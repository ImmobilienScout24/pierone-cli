#!/usr/bin/env python
import sys
from pkg_resources import load_entry_point

if __name__ == '__main__':
    sys.exit(
        load_entry_point('stups-pierone', 'console_scripts', 'pierone')()
    )
