import argparse
import subprocess
import os
import sys
from setuptools import setup, find_packages
from termcolor import cprint

def version_record(flag:str, major_inc:bool=False, minor_inc:bool=False, patch_inc:bool=True, update_msg:str='update version'):
    cprint('version_record ...','yellow')
    ver_file_path = 'package_version.txt'
    if not os.path.exists(ver_file_path):
        subprocess.run(args=['touch', ver_file_path])
        with open(ver_file_path, 'w') as f:
            f.write('0.0.0: init version\n')
            f.close()
    
    if flag == 'read':
        with open(ver_file_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
            f.close()
        print(lines)
        return lines[-1].split(': ')[0]
    elif flag == 'write':
        cprint('updating version record ...','yellow')
        with open(ver_file_path, 'a+') as f:
            f.seek(0)
            lastest_version = f.readlines()[-1]
            lv_number_list = lastest_version.split(': ')[0].split('.')
            print(lv_number_list)
            if major_inc:
                lv_number_list[0] = str(int(lv_number_list[0]) + 1)
                lv_number_list[1] = '0'
                lv_number_list[2] = '0'
                new_version = f'{".".join(lv_number_list)}: {update_msg}'
            elif minor_inc :
                lv_number_list[1] = str(int(lv_number_list[1]) + 1)
                lv_number_list[2] = '0'
                new_version = f'{".".join(lv_number_list)}: {update_msg}'
            elif patch_inc:
                lv_number_list[2] = str(int(lv_number_list[2]) + 1)
                new_version = f'{".".join(lv_number_list)}: {update_msg}'
            else:
                print('no version increment is parsed ...')
                sys.exit()
            f.write(f'{new_version}\n')
            f.close()
        cprint(f'new version: {new_version}','yellow')
        return ".".join(lv_number_list)
    elif flag == 'upload':
        cprint('updating version record ...','yellow')
        with open(ver_file_path, 'a+') as f:
            f.seek(0)
            lastest_version = f.readlines()[-1].strip()
            lastest_version = f'{lastest_version} -> uploaded'
            f.write(f'{lastest_version}\n')
            f.close()
        cprint(f'new version: {lastest_version}','yellow')


def get_package_requirements():
    cprint('getting requirements ...', 'yellow')
    with open('dh_backtest/requirements.txt', 'r') as f:
        lines = [line.strip().replace('==', '>=') for line in f.readlines()]
        f.close()
    return lines

if __name__ == "__main__":
    subprocess.run(args=["pipreqs", "dh_backtest", "--force"])
    subprocess.run(args=["rm", "-rf", "dist"])
    setup(
        name                ='dh_backtest',
        version             =version_record('read'),
        packages            =find_packages(include=['dh_backtest', 'dh_backtest.*']),
        install_requires    =get_package_requirements(),
    )