from flask import Flask, render_template, request, jsonify, Response, send_file, redirect
import json
import subprocess
import os
import paramiko
import time
import re
import hjson
from datetime import datetime
import ast
import globals
import sched
import threading
import functools



# import ALL, because of globals.
# Global variables to store SSH clients
sftp_client = False
exec_client = False
log_file = open('log.log', 'a+')

# Create a scheduler
scheduler = sched.scheduler(time.time, time.sleep)


def write_stdout(stdout, instance):
    for line in stdout:
        message = f"update_Application: {line.strip()}"
        write_to_log(log_file, message, instance)

def write_stderr(stderr, instance):
    for line in stderr:
        message = f"ERROR: update_Application: {line.strip()}"
        write_to_log(log_file, message, instance)
        print("err:", line.strip())
    return True

# Load instances from config.hjson
def load_instances():
    try:
        with open('config.hjson', 'r') as file:
            instances_ordered = hjson.load(file)
        return json.loads(json.dumps(instances_ordered))
    except FileNotFoundError:
        #print("Error: HJSON file not found.")
        return []

def write_to_log(log_file, message, instance="none"):
    log_file = log_file
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    #print (instance)
    if instance == "none":
        #print ('none')
        log_file.write(f"{timestamp} - {message} \n")

    else:
        log_file.write(f"{timestamp} - {instance['name']} - {message} \n")

    log_file.flush()  # Flush the buffer after writing each line


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
        message = (f"ssh_connect: ERROR: Unsupported key type or invalid key file")
        write_to_log(log_file, message, instance)
        return jsonify({'success': False, 'error': 'Unsupported key type or invalid key file'})

    return private_key, key_class

#def ssh_connect(instance, log_file, sftp_client=None, exec_client=None, ):
def ssh_connect(instance, log_file):
    global sftp_client, exec_client

    try:
        connected_instance = globals.connected_instance
        # Check if the selected instance matches the currently connected instance
        if connected_instance == instance:
            # Return True to indicate that the connection is already established
            message = (f"ssh_connect: reusing existing ssh connection to {instance['name']}")
            write_to_log(log_file, message, instance)
            return sftp_client, exec_client

        elif connected_instance: #it has data, but not equal to currently selected instance
            #close the old connection
            #print ('close')
            #close_ssh_connect(sftp_client,exec_client,log_file)
            close_ssh_connect(sftp_client,exec_client)

        #start a new connection
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
        globals.connected_instance = instance

        #return True
        try:
            initiate_ssh_timeout_monitor(120, instance)
        except Exception as e:
            write_to_log(log_file, "timeout monitor error", instance)
            print(f'timeout monitor error: {str(e)}')

    except Exception as e:
        message = (f"ssh_connect: ERROR2 {str(e)}")
        write_to_log(log_file, message, instance)
        return jsonify({'success': False, 'error': str(e)})

    return sftp_client, exec_client

# Define a function to schedule the SSH connection closure
def schedule_ssh_connection_closure(timeout, instance, sftp_client, exec_client):
    scheduler.enter(timeout, 1, functools.partial(close_ssh_connect, sftp_client, exec_client))
    write_to_log(log_file, f"SSH connection will be closed after {timeout} seconds of inactivity", instance)
    #print(f"SSH connection will be closed after {timeout} seconds.")

# Define a function to start the scheduler in a separate thread
def start_scheduler(timeout, instance, sftp_client, exec_client):
    # Schedule the SSH connection closure
    schedule_ssh_connection_closure(timeout, instance, sftp_client, exec_client)
    # Start the scheduler
    scheduler.run()

# Call this function whenever you establish a new SSH connection
def initiate_ssh_timeout_monitor(timeout, instance):
    # Create a new thread for the scheduler
    thread = threading.Thread(target=start_scheduler, args=(timeout, instance, sftp_client, exec_client, ))
    # Set the thread as a daemon so it terminates when the main thread exits
    thread.daemon = True
    # Start the thread
    thread.start()

def close_ssh_connect(sftp_client, exec_client):
    print (sftp_client)
    print (exec_client)
    try:
        if sftp_client:
            sftp_client.close()
        if exec_client:
            exec_client.close()

        instance = globals.connected_instance
        write_to_log(log_file, f"SSH connection closed", instance)

        globals.connected_instance = None
        sftp_client = False
        exec_client = False
        #print ('closed ssh connection')
        #return jsonify({'success': True}) #not allowed by flask to return outside application context.

    except Exception as e:
        message = (f"close_ssh_connect: ERROR {str(e)}")
        write_to_log(log_file, message)
        #return jsonify({'success': False, 'error': str(e)}) #not allowed by flask to return outside application context.

def check_bot_running(exec_client, instance):
    #verify if a proces of the bot is running


    #pattern to find the used bot file .py based on the start command
    pattern = r'\b([\w.-]+\.py)\b'
    match = re.search(pattern, f"{instance['ds_start_command']}")
    if match:
        multibotfile = match.group(1)
        print (f"active:{multibotfile}")
    else:
        print ("error in verify_application_active")


    bot_active = False
    stdin, stdout, stderr = exec_client.exec_command(f"ps -u {instance['ssh_user']} -o command | grep -e {multibotfile}")
    for line in stdout:
        if not 'bash' in line and not 'grep -e' in line:
            bot_active = True
    return bot_active

def compare_config_files(instance):
    # Load the contents of the config files


#    if "Already up to date" not in lastmessage:

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
        #set tmux settings
        stdin, stdout, stderr = exec_client.exec_command(f"tmux set -g remain-on-exit on")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)

        #create new tmux window
        stdin, stdout, stderr = exec_client.exec_command(f"tmux new-session -d -s {instance['tmux_window_name']}")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)

        #create new tmux pane
        newcmd = f"tmux new-window -t {instance['tmux_window_name']} -n {instance['tmux_pane_name']} -d -c {instance['ds_location']}"

        stdin, stdout, stderr = exec_client.exec_command(f"{newcmd}")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)

        #do stuff when venv start command is filled
        if instance['venv_start_command']:
            venvstartcmd = f"tmux send -t {instance['tmux_window_name']}:{instance['tmux_pane_name']} 'bash -c \"{instance['venv_start_command']}\"' ENTER"

            stdin, stdout, stderr = exec_client.exec_command(f"{venvstartcmd}")
            for line in stdout:
                message = (f"restart_application: {line.strip()}\n")
                write_to_log(log_file, message, instance)
            for line in stderr:
                message = (f"err restart_application: {line.strip()}\n")
                write_to_log(log_file, message, instance)
            time.sleep(1)

#TODO kill or rename the default pane
        #renamecmd = f"tmux send-keys -t {instance['tmux_window_name']}:bash C-b , rename-window {instance['tmux_pane_name']} Enter"

        #start bot in the pane
        startcmd = f"tmux send -t {instance['tmux_window_name']}:{instance['tmux_pane_name']} 'bash -c \"{commandlineData}\"' ENTER"

        stdin, stdout, stderr = exec_client.exec_command(f"{startcmd}")
        for line in stdout:
            message = (f"restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        for line in stderr:
            message = (f"err restart_application: {line.strip()}\n")
            write_to_log(log_file, message, instance)
        time.sleep(1)

def verify_application_active(exec_client, instance, log_file):

#TODO: NOT IN USE?

    #pattern to find the used bot file .py based on the start command
    pattern = r'\b([\w.-]+\.py)\b'
    match = re.search(pattern, f"{instance['ds_start_command']}")
    if match:
        multibotfile = match.group(1)
        print (f"active:{multibotfile}")
    else:
        print ("error in verify_application_active")

    #verify if no proces of the bot is stil running
    bot_active = False
    stdin, stdout, stderr = exec_client.exec_command(f"ps -u {instance['ssh_user']} -o command | grep -e '{multibotfile}'")
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

def find_strategies_in_multibot(instance, exec_client, log_file):
    # Initialize an empty list to store the strategies
    strategies = []

    #pattern to find the used bot file .py based on the start command
    pattern = r'\b([\w.-]+\.py)\b'
    match = re.search(pattern, f"{instance['ds_start_command']}")
    if match:
        multibotfile = f"{instance['ds_location']}" + match.group(1)
        print (multibotfile)
    else:
        print ("error in find_strategies_in_multibot")

    # Execute the command to read the file contents
    _, stdout, _ = exec_client.exec_command(f"cat {multibotfile}")

    # Read the output from the command
    file_contents = stdout.read().decode('utf-8')  # Decode bytes to string
    #print (file_contents)

    tree = ast.parse(file_contents, filename=multibotfile)

    # Define a visitor to traverse the AST and find the desired function
    class FunctionVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node.name == 'get_available_strategies':
                # If the function is found, extract the strategies
                for statement in node.body:
                    if isinstance(statement, ast.Return):
                        if isinstance(statement.value, ast.List):
                            for element in statement.value.elts:
                                if isinstance(element, ast.Str):
                                    strategies.append(element.s)

    # Visit the AST using the FunctionVisitor
    visitor = FunctionVisitor()
    visitor.visit(tree)

    return strategies
