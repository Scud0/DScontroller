from flask import Flask, render_template, request, jsonify, Response, send_file, redirect
import json
import subprocess
import os
import paramiko
import time
import re
import hjson
from datetime import datetime

from io import StringIO
from paramiko import RSAKey, Ed25519Key, ECDSAKey, DSSKey, PKey
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, dsa, rsa, ec


# Load instances from config.hjson
def load_instances():
    try:
        with open('config.hjson', 'r') as file:
            instances_ordered = hjson.load(file)
        return json.loads(json.dumps(instances_ordered))
    except FileNotFoundError:
        print("Error: HJSON file not found.")
        return []
        #return jsonify({'success': False, 'error': "Error: HJSON file not found."})

def write_to_log(log_file, message, instance="none"):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    #print (instance)
    if instance == "none":
        #print ('none')
        log_file.write(f"{timestamp} - {message} \n")

    else:
        log_file.write(f"{timestamp} - {instance['name']} - {message} \n")

    log_file.flush()  # Flush the buffer after writing each line

# def load_private_key(keyfile_path):
#     """
#     Load the private key from the specified key file.
#     Supports both RSA and Ed25519 key types.
#     """
#     # Determine the key type based on the file path
#     if keyfile_path.endswith('.pub'):
#         keyfile_path = keyfile_path[:-4]  # Remove .pub extension if present
#
#     # Load the private key
#     with open(keyfile_path, 'r') as key_file:
#         key_data = key_file.read()
#
#         # Determine the key type
#         if 'BEGIN RSA PRIVATE KEY' in key_data:
#             key_type = 'RSA'
#         elif 'BEGIN OPENSSH PRIVATE KEY' in key_data:
#             key_type = 'Ed25519'
#         else:
#             raise ValueError("Unsupported key type")
#
#         # Load the private key based on the key type
#         if key_type == 'RSA':
#             private_key = paramiko.RSAKey.from_private_key_file(keyfile_path)
#         elif key_type == 'Ed25519':
#             private_key = paramiko.Ed25519Key(filename=keyfile_path)
#         else:
#             raise ValueError("Unsupported key type")
#
#     return private_key



def determine_keyfile_type(instance, log_file, password=None):
    key_classes = [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey]
    private_key = None

    for key_class in key_classes:
        try:
            private_key = key_class.from_private_key_file(instance['ssh_keyfile'], password=password)
            break  # Stop the loop if successful
            # message = (f"ssh_connect: using key class: {key_class}")
            # write_to_log(log_file, message, instance)
        except paramiko.ssh_exception.PasswordRequiredException:
            pass
        except paramiko.ssh_exception.SSHException:
            pass

    if not private_key:
        raise ValueError("Unsupported key type or invalid key file.")

    return private_key, key_class

def ssh_connect(instance, log_file, sftp_client=None, exec_client=None, ):
    try:
        #print('test')

        #rint (private_key)

        #print (instance)
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Check if a keyfile is provided
        if 'ssh_keyfile' in instance and instance['ssh_keyfile']:
            # Authenticate using keyfile
            #print ('key')
            #private_key = paramiko.RSAKey.from_private_key_file(instance['ssh_keyfile'])

            private_key, key_class = determine_keyfile_type(instance, log_file, password=None)

            ssh_client.connect(hostname=instance['ssh_host'],
                                port=instance['ssh_port'],
                                username=instance['ssh_user'],
                                pkey=private_key)

            message = (f"ssh_connect: using keyfile logon with class: {key_class}")
            write_to_log(log_file, message, instance)

        elif 'ssh_pass' in instance and instance['ssh_pass']:
            # Authenticate using password
            ssh_client.connect(hostname=instance['ssh_host'],
                                port=instance['ssh_port'],
                                username=instance['ssh_user'],
                                password=instance.get('ssh_pass', None))

            message = (f"ssh_connect: using password logon")
            write_to_log(log_file, message, instance)

        else:
            message = (f"ssh_connect: ERROR: No password or keyfile given")
            write_to_log(log_file, message, instance)
            return jsonify({'success': False, 'error': 'No password or keyfile given'})

        sftp_client = ssh_client.open_sftp()
        exec_client = ssh_client
    except Exception as e:
        message = (f"ssh_connect: ERROR {str(e)}")
        write_to_log(log_file, message, instance)
        return jsonify({'success': False, 'error': str(e)})

    return sftp_client, exec_client

def close_ssh_connect(sftp_client,exec_client):
        sftp_client.close()
        exec_client.close()

def check_bot_running(exec_client, instance):
    #verify if a proces of the bot is running
    bot_active = False
    stdin, stdout, stderr = exec_client.exec_command(f"ps -u {instance['ssh_user']} -o command | grep -e 'multi_bot.py'")
    for line in stdout:
        if not 'bash' in line and not 'grep -e' in line:
            bot_active = True
    return bot_active

def compare_config_files(instance, message, log_file):
    # Load the contents of the config files

    if "Already up to date" not in message:

        sftp_client, exec_client = ssh_connect(instance, log_file)

        # Fetch the contents of the config.json file
        stdin, stdout, stderr = exec_client.exec_command(f"cat {instance['ds_config_file']}")
        config_data = json.loads(stdout.read().decode('utf-8'))
        #print ("config\n")
        #print (config_data)

        stdin, stdout, stderr = exec_client.exec_command(f"cat {instance['ds_location']}configs/config_example.json")
        example_data = json.loads(stdout.read().decode('utf-8'))
        #print ("example\n")
        #print (example_data)

        # Get the keys of each file
        config_keys = set(config_data.keys())
        example_keys = set(example_data.keys())

        # Check for mismatched keys
        mismatched_keys = config_keys.symmetric_difference(example_keys)

        # If there are mismatched keys, do something
        if mismatched_keys:
            #print("Mismatched keys found:")
            message = (f"update_Application: Mismatched config keys found:")
            write_to_log(log_file, message, instance)

            for key in mismatched_keys:
                if key in config_keys:
                    #print(f"Key '{key}' exists in config.json but not in config.example.json")
                    message = (f"Key '{key}' exists in config.json but not in config.example.json")
                    write_to_log(log_file, message, instance)
                else:
                    #print(f"Key '{key}' exists in config.example.json but not in config.json")
                    message = (f"Key '{key}' exists in config.example.json but not in config.json")
                    write_to_log(log_file, message, instance)
        else:
            #print("No mismatched keys found.")
            message = (f"update_Application: all good, no config mismatches found")
            write_to_log(log_file, message, instance)

def func_stop_application(exec_client, instance, log_file):
    #close tmux pane and bot
    stdin, stdout, stderr = exec_client.exec_command(f"tmux list-windows -t {instance['tmux_window_name']}")
    for line in stdout:
        windownumber = (re.match("^.*(?=(\:))", line))

        killcmd = f"tmux kill-window -t {instance['tmux_window_name']}:{windownumber[0]}"
        #logging.warning('killcmd:' + killcmd)
        stdin, stdout, stderr = exec_client.exec_command(f"{killcmd}")
        time.sleep(1)


def func_start_application(exec_client, instance, bot_active, log_file, commandlineData):
    #start bot
    if not bot_active:
        stdin, stdout, stderr = exec_client.exec_command(f"tmux set -g remain-on-exit on")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)
        stdin, stdout, stderr = exec_client.exec_command(f"tmux new-session -d -s {instance['tmux_window_name']}")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)
        newcmd = f"tmux new-window -t {instance['tmux_window_name']} -n {instance['tmux_pane_name']} -d -c {instance['ds_location']}"

        #TODO kill or rename the default pane
        #renamecmd = f"tmux send-keys -t {instance['tmux_window_name']}:bash C-b , rename-window {instance['tmux_pane_name']} Enter"

        #start in the pane
        startcmd = f"tmux send -t {instance['tmux_window_name']}:{instance['tmux_pane_name']} 'bash -c \"{commandlineData}\"' ENTER"
        #print (startcmd)

        stdin, stdout, stderr = exec_client.exec_command(f"{newcmd}")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)

        time.sleep(2)
        stdin, stdout, stderr =exec_client.exec_command(f"{startcmd}")
        time.sleep(2)

        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)

def verify_application_active(exec_client, instance, log_file):
    #verify if no proces of the bot is stil running
    bot_active = False
    stdin, stdout, stderr = exec_client.exec_command(f"ps -u {instance['ssh_user']} -o command | grep -e 'multi_bot.py'")
    for line in stdout:
        if not 'bash' in line and not 'grep -e' in line:
            bot_active = True
            # message = (f"stop_application: ERROR: I was unable to shutdown the bot. Check manually!")
            # write_to_log(log_file, message, instance)
            # return jsonify({'success': False, 'error': 'I was unable to shutdown the bot. Check manually'})
            return bot_active
    return bot_active

def verify_application_version(exec_client, instance, log_file):
    update_available = False

    stdin, stdout, stderr = exec_client.exec_command(f"cd {instance['ds_location']} && git rev-parse HEAD | cut -c1-7")
    for line in stdout:
        local_version = line.strip()

    stdin, stdout, stderr = exec_client.exec_command(f"cd {instance['ds_location']} && git ls-remote https://github.com/donewiththedollar/directionalscalper HEAD | cut -c1-7")
    for line in stdout:
        remote_version = line.strip()

    if local_version == remote_version:
        update_available = False
    else:
        update_available = True

    message = (f"local version: {local_version}; remote version: {remote_version}; update available: {update_available}")
    write_to_log(log_file, message, instance)
    return update_available

def update_ds_start_command(instance, commandlineData, log_file):
    instance_id = instance['id']

    # Read the contents of config.hjson
    with open('config.hjson', 'r') as file:
        config_data = hjson.load(file)

    # Find the instance with the specified ID
    for instance in config_data['instances']:
        if instance['id'] == instance_id:
            # Update the ds_start_command for the instance
            instance['ds_start_command'] = commandlineData

            message = (f"config_update: updated ds start command in config file")
            write_to_log(log_file, message, instance)
            break
    else:
        message = (f"config_update: error: unable to excecute")
        write_to_log(log_file, message, instance)
        return jsonify({'success': False, 'error': 'config_update: error: unable to excecute'})

    # Write the modified dictionary back to config.hjson
    with open('config.hjson', 'w') as file:
        hjson.dump(config_data, file, indent=4)

    return jsonify({'success': True})

