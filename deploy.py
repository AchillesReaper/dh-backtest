import os
import argparse
import subprocess
from setup import version_record
from dotenv import load_dotenv

load_dotenv()
TWINE_USERNAME = os.getenv('TWINE_USERNAME')
TWINE_PASSWORD = os.getenv('TWINE_PASSWORD')


def build_package():
    subprocess.run(args=["python", "setup.py", "sdist", "bdist_wheel"])


def publish_package():
    version_record('upload')
    subprocess.run(args=["twine", "upload", "-u", TWINE_USERNAME, "-p", TWINE_PASSWORD, "dist/*"])
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Deploy script for building or publishing the package.')
    parser.add_argument('-b', '--build', action='store_true', help='Build the package')
    parser.add_argument('-p', '--publish', action='store_true', help='Publish the package to PyPi')
    args = parser.parse_args()
    
    if args.build:
        build_package()
    elif args.publish:
        publish_package()
    else:
        print("An execution command is needed. Use --help for more information.")