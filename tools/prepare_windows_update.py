"""Write the versioned package manifest after building, before archiving."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from windows_update import make_manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--version',default='0.5.1')
    args=parser.parse_args()
    make_manifest(args.folder,args.version)
