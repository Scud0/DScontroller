from flask import Flask, render_template, request, jsonify, Response, send_file, redirect
from functions import *
import json
import subprocess
import os
import paramiko
import time
import re
import hjson
from datetime import datetime
import globals

app = Flask(__name__)

# Open the log file in append mode
try:
    # Open the log file in append mode
    log_file = open('log.log', 'a+')
except FileNotFoundError:
    # If the file doesn't exist, create it
    log_file = open('log.log', 'w+')



@app.route('/')
def index():
    # Clear the log file
    bot_instances = load_instances()
    open('log.log', 'w').close()

    if bot_instances == []:
        message = (f"load config: ERROR: config file empty! Did you create it?")
        write_to_log(log_file, message)

    return render_template('index.html', instances=bot_instances)

@app.route('/get_data', methods=['POST'])
def get_data():
    bot_instances = load_instances()
    instance_id = int(request.form['instance_id'])
    instance = next((inst for inst in bot_instances['instances'] if inst['id'] == instance_id), None)
    #update_available = False #default to false
    # print (instance)
    # time.sleep(60)
    if instance:
        try:
            sftp_client, exec_client = ssh_connect(instance, log_file)

            bot_active = check_bot_running(exec_client, instance)

            try:
                config_file_path = instance['ds_config_file']
                with sftp_client.open(config_file_path, 'r') as file:
                    config_data = json.load(file)
            except Exception as e:
                message = (f"get_data: ERROR: I could not find the specified config file [ds_config_file]")
                write_to_log(log_file, message, instance)
                close_ssh_connect(sftp_client,exec_client)
                return jsonify({'error': 'config file not found'})

            commandline_data = instance['ds_start_command']

            #close_ssh_connect(sftp_client,exec_client)

            update_available = verify_application_version(exec_client, instance, log_file)

            #update_available = True #debug

            strategies = find_strategies_in_multibot(instance, exec_client, log_file)
            message = (f"get_data: available strategies: {strategies}")
            write_to_log(log_file, message, instance)

            # Serialize the data without sorting keys
            response_data = json.dumps({'config_data': config_data, 'commandline_data': commandline_data, 'bot_status': bot_active, 'update_available': update_available}, indent=2, sort_keys=False)

            message = (f"get_data: done")
            write_to_log(log_file, message, instance)
            return Response(response_data, content_type='application/json')

        except Exception as e:
            message = (f"get_data: ERROR {str(e)}")
            write_to_log(log_file, message, instance)

            try:
                close_ssh_connect(sftp_client,exec_client)

            except:
                pass

            return jsonify({'error': str(e)})

    else:
        message = (f"get_data: ERROR1 {str(e)}")
        write_to_log(log_file, message, instance)

        close_ssh_connect(sftp_client,exec_client)
        return jsonify({'error': 'Instance not found'})

@app.route('/get_config', methods=['POST'])
def get_config():
    instances_data = load_instances()

    # Return instances_data as a JSON string
    response_data = json.dumps({'config_data': instances_data}, indent=2)

    message = "get_config: ok"
    write_to_log(log_file, message)

    return Response(response_data, content_type='application/json')


@app.route('/save_json', methods=['POST'])
def save_json():
    try:
    #1: check if valid json
    #2: determine config type (ds config OR controller config
    #3.1: ds config code
    #3.2: controller code
        new_json = request.form['json']
        #print (new_json)

        # Check if the new JSON is valid JSON
        try:
            json.loads(new_json)
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'error': f'Invalid JSON: {e}'})

        new_json_dict = json.loads(new_json)
        if new_json_dict.get('api') is not None:
            # print ("its a remote config.json")
            try:
                bot_instances = load_instances()
                instance_id = int(request.form['instance_id'])
                instance = next((inst for inst in bot_instances['instances'] if inst['id'] == instance_id), None)

                sftp_client, exec_client = ssh_connect(instance, log_file, globals.connected_instance)

                config_file_path = instance['ds_config_file']
                with sftp_client.open(config_file_path, 'w') as file:
                    file.write(new_json)

                message = (f"save_config: succesfully saved the config on the remote server")
                write_to_log(log_file, message, instance)
                return jsonify({'success': True})

            except Exception as e:
                message = (f"save_config: ERROR: {str(e)}")
                write_to_log(log_file, message, instance)
                return jsonify({'success': False, 'error': str(e)})

        elif new_json_dict.get('instances') is not None:
            try:
                # print ("its local controller hjson")

                # Get the updated instances data from the form
                updated_instances_data = new_json

                # Write the updated data to the instances.hjson file
                with open('config.hjson', 'w') as file:
                    file.write(updated_instances_data)

                message = (f"save_config: succesfully saved the instances config")
                write_to_log(log_file, message)

                load_instances() #reload the instances for the selector.
                # index()

                return jsonify({'success': True})

            except Exception as e:
                message = (f"save_config: ERROR: {str(e)}")
                write_to_log(log_file, message)
                return jsonify({'success': False, 'error': str(e)})


        else:
            # print("None of the conditions are True")
            message = (f"save_config: ERROR: could not dermine config type")
            write_to_log(log_file, message, instance)
            return jsonify({'success': False, 'error': str(e)})


    except Exception as e:
        message = (f"save_config: ERROR: {str(e)}")
        write_to_log(log_file, message)
        return jsonify({'success': False, 'error': str(e)})


@app.route('/restart_application', methods=['POST'])
def restart_application():
    """
    1. match Startcommand commandlineData against instance[ds_start_command]. if not equal, update config.hjson.
    2. def stop_application
    3. def verify_application_active
    4. def start_application
    5. def verify_application_active
    6. log
    """
    bot_instances = load_instances()
    instance_id = int(request.form['instance_id'])
    commandlineData = request.form['commandLineData']
    instance = next((inst for inst in bot_instances['instances'] if inst['id'] == instance_id), None)
    #print (instance)
    #time.sleep(60)
    if instance:
        try:
            write_to_log(log_file, "(re)start_application: restarting, hold on", instance)
            """
            1. check if commandlineData is equal to instance['ds_start_command'].
            2.1 if not. save into config.hjson.
            2.2 if equal, continue
            """
            if commandlineData != instance['ds_start_command']:
                update_ds_start_command(instance, commandlineData, log_file)

            # #save startcommand file
            # commandline_file_path = instance['ds_start_commandline_file']
            # with sftp_client.open(commandline_file_path, 'w') as file:
            #     file.write(commandlineData)
            #     print (commandlineData)

            #open connection to vps
            sftp_client, exec_client = ssh_connect(instance, log_file, globals.connected_instance)
            #time.sleep(60)

            func_stop_application(exec_client, instance, log_file)

            bot_active = verify_application_active(exec_client, instance, log_file)
            if bot_active:
                message = (f"stop_application: ERROR: I was unable to shutdown the bot. Check manually!")
                write_to_log(log_file, message, instance)
                return jsonify({'success': False, 'error': 'I was unable to shutdown the bot. Check manually'})

            func_start_application(exec_client, instance, bot_active, log_file, commandlineData)

            bot_active = verify_application_active(exec_client, instance, log_file)
            if not bot_active:
                message = (f"(re)start_application: ERROR: I was unable to  start the bot. Check manually!")
                write_to_log(log_file, message, instance)
                return jsonify({'success': False, 'error': 'I was unable to start the bot. Check manually'})

            message = (f"(re)start_application: succesfully (re)started the application")
            write_to_log(log_file, message, instance)
            return jsonify({'success': True})

        except Exception as e:
            write_to_log(log_file, f"(re)start_application: ERROR: {str(e)}", instance)
            return jsonify({'success': False, 'error': str(e)})
    else:
        write_to_log(log_file, f"(re)start_application: ERROR: {str(e)}", instance)
        return jsonify({'success': False, 'error': 'Instance not found'})

@app.route('/stop_application', methods=['POST'])
def stop_application():
    bot_instances = load_instances()
    instance_id = int(request.form['instance_id'])
    instance = next((inst for inst in bot_instances['instances'] if inst['id'] == instance_id), None)
    #print (instance)
    if instance:
        try:
            write_to_log(log_file, "stop_application: stopping, hold on", instance)
            #open connection to vps
            sftp_client, exec_client = ssh_connect(instance, log_file, globals.connected_instance)

            func_stop_application(exec_client, instance, log_file)

            bot_active = verify_application_active(exec_client, instance, log_file)
            if bot_active:
                message = (f"stop_application: ERROR: I was unable to shutdown the bot. Check manually!")
                write_to_log(log_file, message, instance)
                return jsonify({'success': False, 'error': 'I was unable to shutdown the bot. Check manually'})

            write_to_log(log_file, "stop_application: stop done", instance)
            return jsonify({'success': True})
        except Exception as e:
            write_to_log(log_file, f"stop_application: ERROR: {str(e)}", instance)
            return jsonify({'success': False, 'error': str(e)})
    else:
        write_to_log(log_file, f"stop_application: ERROR: {str(e)}", instance)
        return jsonify({'success': False, 'error': 'Instance not found'})

@app.route('/update_application', methods=['POST'])
def update_application():
    bot_instances = load_instances()
    instance_id = int(request.form['instance_id'])
    instance = next((inst for inst in bot_instances['instances'] if inst['id'] == instance_id), None)
    if instance:
        try:
            sftp_client, exec_client = ssh_connect(instance, log_file, globals.connected_instance)

            # SSH command to perform git pull
            git_pull_command = f"cd {instance['ds_location']} && git pull"

            stdin, stdout, stderr = exec_client.exec_command(f"{git_pull_command}")
            # for line in stdin:
            #     print("in:", line.strip())
            for line in stdout:
                #logger.critical(f"{line.strip()}")
                message = (f"update_Application: {line.strip()}")
                write_to_log(log_file, message, instance)
                print("out:", line.strip())

            for line in stderr:
                #logger.critical(f"Error: {line.strip()}")
                message = (f"ERROR: update_Application: {line.strip()}")
                write_to_log(log_file, message, instance)
                print("err:", line.strip())
                error_messages = True
            if error_messages:
                return jsonify({'success': False, 'error': 'failed to update, check the log'})

            compare_config_files(instance, message,log_file)

            get_data() #reload data after update

            write_to_log(log_file, f"update_application: update done", instance)
            write_to_log(log_file, f"update_application: don't forget to (re)start)", instance)

            return jsonify({'success': True})
        except Exception as e:
            write_to_log(log_file, f"update_application: ERROR: {str(e)}", instance)
            return jsonify({'success': False, 'error': str(e)})
    else:
        write_to_log(log_file, f"update_application: ERROR: {str(e)}", instance)
        return jsonify({'success': False, 'error': 'Instance not found'})

@app.route('/get_log')
def get_log():
    # Send the log file as a response
    return send_file('log.log')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5431)
