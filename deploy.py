import os
import argparse
import subprocess
from setup import version_record
from dotenv import load_dotenv

load_dotenv()
TWINE_USERNAME = os.getenv('TWINE_USERNAME')
TWINE_PASSWORD = os.getenv('TWINE_PASSWORD')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Deploy script for building or publishing the package.')
    parser.add_argument('-b', '--build', action='store_true', help='Build the package')
    parser.add_argument('-p', '--publish', action='store_true', help='Publish the package to PyPi')
    parser.add_argument('-mji', '--major_increment', action='store_true', help='denote if this is a major version update')
    parser.add_argument('-mii', '--minor_increment', action='store_true', help='denote if this is a minor version update')
    parser.add_argument('-msg', '--update_msg', nargs=1, help='denote the update message')
    args = parser.parse_args()
    
    if args.build:
        if args.update_msg:
            if args.major_increment:
                version_record('write', major_inc=True, update_msg=args.update_msg[0])
            elif args.minor_increment:
                version_record('write', minor_inc=True, update_msg=args.update_msg[0])
            else:
                version_record('write', update_msg=args.update_msg[0])
        else:
            if args.major_increment:
                version_record('write', major_inc=True)
            elif args.minor_increment:
                version_record('write', minor_inc=True)
            else:
                version_record('write')
        subprocess.run(args=["python", "setup.py", "sdist", "bdist_wheel"])
    elif args.publish:
        version_record('upload')
        subprocess.run(args=["twine", "upload", "-u", TWINE_USERNAME, "-p", TWINE_PASSWORD, "dist/*"])
        subprocess.run(args=["rm", "-rf", "build", "dist", "dh_backtest.egg-info"])
        subprocess.run(args=["find", ".", "-type", "d", "-name", "__pycache__", "-exec", "rm", "-rf", "{}", "+"])

    else:
        print("An execution command is needed. Use --help for more information.")
    
