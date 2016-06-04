#!/usr/bin/env python3
import rtorrent

import threading
import time
import imp
import subprocess
import logging
import xmlrpc
import math
import os
import os.path
import argparse
import queue
from pprint import pprint
from http.client import RemoteDisconnected

# imp.find_module('rtorrent.conf')
conf = imp.load_source('conf', 'rtorrent.conf')

parser = argparse.ArgumentParser(description='syncs remote rtorrent')
parser.add_argument('--test', action='store_true',
                    help='simulates transfers', default=False)
parser.add_argument('--debug', action='store_true',
                    help='debug output', default=False)

args = parser.parse_args()

jobs = queue.Queue()


rt = rtorrent.RTorrent(conf.url)
logging.basicConfig()
log = logging.getLogger()
if args.debug:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)
workers = []

class Worker(threading.Thread):
    def run(self):
        print('start worker: %s' % self.name)
        while True:
            try:
                job = jobs.get()
                print('#%s running job: %s' % (self.name, job))
                subprocess.check_output(job)
            except Exception as e:
                print("error in running job: %s" % e)

class Job(list):
    pass

def rpc_call(key, *args):
    parts = key.split('.')
    obj = rt.get_conn()
    for p in parts:
        obj = getattr(obj, p)
    # for some strange reason, the call returns RemoteDisconnect sometimes, maybe after successful
    # set... anyway, retry the call seems to work
    for i in range(3):
        try:
            return obj.__call__(*args)
        except RemoteDisconnected as e:
            if i == 2:
                raise

from operator import itemgetter, attrgetter, methodcaller


def cleanup(opts = None):
    if not opts:
        opts = {}
    df_out = subprocess.check_output(SSH_COMMAND +
                                     ['df', '-m', '-P', conf.remote_folder])
    df = [x.split() for x in df_out.splitlines()]
    print(df)
    print(df[0].index(b'Available'))
    free = int(df[1][df[0].index(b'Available')])

    if free > conf.free_mb:
        return
    files_output = subprocess.check_output(SSH_COMMAND +
                                           ['find', conf.remote_folder, '-type', 'f',
                                           '-printf', '"%T@\\t%s\\t%p\\0"'])
    files = list(filter(lambda x: len(x) == 3, [x.split(b'\t', maxsplit=2) for x in files_output.split(b'\0')]))
    for f in files:
        if len(f) != 3:
            continue
        f[0] = time.gmtime(float(f[0]))
        f[1] = int(f[1])

    files = sorted(files, key=lambda x: x[0])
    # filter out used files in current torrents
    to_delete = []

    # pprint(new_list)
    need_free = max(conf.free_mb - free, 0)
    will_free = 0
    log.info('need to free %s mb' % need_free)

    for f in files:
        if will_free >= need_free:
            break
        fname = f[2].decode('utf-8', errors='ignore')
        if fname in opts['all_files']:
            log.debug("found %s in used files, skip" % fname)
            continue

        to_delete.append(fname)
        will_free += f[1]

    if len(to_delete):
        log.info('will_delete %s' % ' '.join(to_delete))
        if not args.test:
            subprocess.call(SSH_COMMAND +
                            ['rm', '-f'] + to_delete)

def check_files():
    rv = {'all_files': []}
    for torrent in rt.get_torrents():
        log.info('processing %s' % torrent.info_hash)
        print('----------------------------------')
        i = 0
        files = list(torrent.get_file_metadata())
        print('processing %s (%s)' % (torrent.info_hash, len(files)))
        for i, xm in enumerate(files):
            meta = xm.results
            print(meta)
            path = meta['get_path']
            rv['all_files'].append(meta['get_frozen_path'])
            if os.path.splitext(path)[1] == '.meta':
                log.debug('ignore meta file')
                break

            print("#%s - %s - %s - %s" %(i, path,
                                   meta['get_size_chunks'],
                                   meta['get_completed_chunks']))
            print(meta['get_path_depth'],meta['get_path_components'], meta['get_frozen_path'] )
            if meta['get_size_chunks'] == meta['get_completed_chunks']:
                print("complete")

            prefix = len(files) > 1 and os.path.splitext(os.path.basename(files[0].results['get_path']))[0] or ''

            check_path = os.path.join(conf.sync_folder, prefix, path)

            print(check_path)
            transfer_required = False
            if not os.path.exists(check_path) or os.path.getsize(check_path) != meta['get_size_bytes']:
                # pardir, suf = os.path.split()
                pardir = os.path.split(check_path)[0]
                if not os.path.exists(pardir):
                    print('create %s' % pardir)
                    if not args.test:
                        os.makedirs(pardir)
                if not args.test:
                    job = Job(['rsync', '-e', ' '.join(SSH_COMMAND), '-av',
                               "%s:'%s'" % (conf.rsync_host, meta['get_frozen_path']),
                               check_path])
                    job.hash = torrent.info_hash
                    jobs.put(job)
                transfer_required = True

            # cleanup
            print('trans %s' %transfer_required)
            if not transfer_required:
                if not any((path.startswith(x) for x in conf.persistent_folders)) and \
                   conf.target_ratio is not None and \
                   torrent.get_upload_total()/torrent.get_download_total() > conf.target_ratio:
                    print("should stop")
                    rpc_call('d.stop', torrent.info_hash)
                    print('should remove')
    return rv


def run_loop():
    print('starting jobs')
    for i in range(0, getattr(conf, 'prallel', 1)):
        w = Worker(name='worker #%s' % i)
        w.daemon = True
        w.start()
        workers.append(w)
    while True:
        started = time.time()
        state = check_files()
        cleanup(state)

        print(conf.check_interval - (time.time() - started))
        time.sleep(max(conf.check_interval - (time.time() - started), 0))


if __name__ == '__main__':
    run_loop()
