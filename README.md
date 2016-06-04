rtorrent-syncer
---------------

***THIS IS ALPHA SOFTWARE. IT WILL DELETE FILES***

rtorrent-syncer synchronizes and manages a remote rtorrent client (in a remote VM for example) with
a local storage server on which the script runs.
it requires python 3.x.


Functionality
=============

The script syncs the files as soon as the file finishes from your rtorrent host via rsync over ssh
from your rtorrent host. This is on file basis, not on a torrent basis. Files not yet finished are not
started to be synced.
The torrent is if not flagged specially is removed after the ratio is reached.
When a threshold on free space is reached, the oldest files not part of a torrent are deleted.

TODO
====

 * change to [pyrocore](https://github.com/pyroscope/pyrocore)

Installation
============

enable xmlrpc api on your rtorrent host according to feq.
copy rtorrent-example.conf to rtorrent.conf (it is a python file) and adjust.

```sh
python3 rtorrent-syncer.py
```
