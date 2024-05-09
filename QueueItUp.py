import multiprocessing
from multiprocessing import Process
import gradio
import os
import re
import sys
import time
import math
import json
import ctypes
import shutil
import logging
import tkinter
import datetime
import platform
import threading
import subprocess
import configparser
from tkinter.filedialog import askdirectory
from tkinter import filedialog, Text, font, Toplevel, messagebox, PhotoImage, Tk, Canvas, Scrollbar, Frame, Label, Button
from argparse import ArgumentParser
from io import BytesIO
import facefusion.globals
from facefusion import core
#import facefusion.core as core
from facefusion import core, audio, content_analyser, config, download, execution, face_analyser, face_helper, face_masker, face_store, ffmpeg, filesystem, installer, logger, memory, metadata, normalizer, process_manager, statistics, typing, thread_helper, vision, voice_extractor, wording
from facefusion.processors.frame import globals as frame_processors_globals#, choices as frame_processors_choices, core as frame_core, typings as frame_typings
from facefusion.processors.frame.modules import face_debugger, face_enhancer, face_swapper, frame_colorizer, frame_enhancer, lip_syncer
from facefusion.uis.components import about, frame_processors, frame_processors_options, execution, execution_thread_count, execution_queue_count, memory, temp_frame, output_options, common_options, source, target, output, preview, trim_frame, face_analyser, face_selector, face_masker


def pre_check() -> bool:
    return True

def pre_render() -> bool:
    return True


#Globals and toggles
script_root = os.path.dirname(os.path.abspath(__file__))
print("Script Root:", script_root)
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_root)))
# Appending 'QueueItUp' to the adjusted base directory
user_dir = "QueueItUp"
working_dir = os.path.normpath(os.path.join(base_dir, user_dir))
media_cache_dir = os.path.normpath(os.path.join(working_dir, "mediacache"))
thumbnail_dir = os.path.normpath(os.path.join(media_cache_dir, "thumbnails"))
jobs_queue_file = os.path.normpath(os.path.join(working_dir, "jobs_queue.json"))

debugging = True
system_logs= True
history_logs= True
keep_completed_jobs = True
ADD_JOB_BUTTON = gradio.Button("Add Job ", variant="primary")
RUN_JOBS_BUTTON = gradio.Button("Run Jobs", variant="primary")
EDIT_JOB_BUTTON = gradio.Button("Edit Jobs")
#status_priority = {'editing': 0, 'pending': 1, 'failed': 2, 'executing': 3, 'completed': 4}
create_and_verify_json = 0
JOB_IS_RUNNING = 0
JOB_IS_EXECUTING = 0
PENDING_JOBS_COUNT = 0
CURRENT_JOB_NUMBER = 0
image_references = {}
    # ANSI Color Codes     
RED = '\033[91m'     #use this  
GREEN = '\033[92m'     #use this  
YELLOW = '\033[93m'     #use this  
BLUE = '\033[94m'     #use this  
ENDC = '\033[0m'       #use this    Resets color to default


def custom_print(*msgs):
    # Join all arguments into a single message string
    message = " ".join(str(msg) for msg in msgs)

    # ANSI Color Codes
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

    # Mapping of ANSI codes to tkinter text widget tags
    ansi_to_tag = {
        RED: 'red',
        GREEN: 'green',
        YELLOW: 'yellow',
        BLUE: 'blue',
        ENDC: 'end'
    }

    print(message)  # Print to terminal with ANSI coloring


custom_print("Working Directory:", working_dir)
custom_print("Media Cache Directory:", media_cache_dir)
custom_print("Jobs Queue File:", jobs_queue_file)

def get_values_from_globals(state_name):
   # List all modules which states we want to capture

    modules = [
        facefusion.globals, core, audio, content_analyser, config, execution, face_analyser, face_helper, face_masker, face_store, normalizer, process_manager, thread_helper, vision, voice_extractor,frame_processors_globals, common_options, execution_queue_count, execution_thread_count, face_selector, frame_processors, frame_processors_options, memory, output, output_options, preview, source, target, typing, temp_frame, trim_frame
    ]
    state_dict = {}
    for module in modules:
        for attr in dir(module):
            if not attr.startswith("__") and not callable(getattr(module, attr)):
                value = getattr(module, attr)
                try:
                    json.dumps(value) 
                    state_dict[attr] = value 
                except TypeError:
                    continue 
    if debugging:
        with open(os.path.join(working_dir, f"{state_name}.txt"), "w") as file:
            for key, val in state_dict.items():
                file.write(f"{key}: {val}\n")
        custom_print(f"{state_name}.txt created")
    return state_dict

def create_and_verify_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as json_file:  
                json.load(json_file)
        except json.JSONDecodeError:
            backup_path = file_path + ".bak"
            shutil.copy(file_path, backup_path)
            custom_print(f"Backup of corrupt JSON file saved as '{backup_path}'. Please check it for salvageable data.\n\n")
            with open(file_path, "w") as json_file:
                json.dump([], json_file)
            custom_print(f"Original JSON file '{file_path}' was corrupt and has been reset to an empty list.\n\n")
    else:
        with open(file_path, "w") as json_file:
            json.dump([], json_file)
        custom_print(f"JSON file '{file_path}' did not exist and has been created.")

def load_jobs(file_path):
    with open(file_path, 'r') as file:
        jobs = json.load(file)
    return jobs

def save_jobs(file_path, jobs):
    with open(file_path, 'w') as file:
        json.dump(jobs, file, indent=4)
      
        
def count_existing_jobs():
    global PENDING_JOBS_COUNT
    jobs = load_jobs(jobs_queue_file)
    PENDING_JOBS_COUNT = len([job for job in jobs if job['status'] in ['pending', 'editing']])
    return PENDING_JOBS_COUNT

def print_existing_jobs():

    count_existing_jobs()
    if JOB_IS_RUNNING:
        message = f"There is {PENDING_JOBS_COUNT + JOB_IS_RUNNING} job(s) being Processed - Click Add Job to Queue more Jobs"
    else:
        if PENDING_JOBS_COUNT > 0:
            message = f"There is {PENDING_JOBS_COUNT + JOB_IS_RUNNING} job(s) in the queue - Click Run Queue to Execute Them, or continue adding more jobs to the queue"
        else:
            message = f"There is 0 job(s) in the queue - Click Add Job instead of Start"
    custom_print(message + "\n\n")
    

def check_for_completed_failed_or_aborted_jobs():
    count_existing_jobs()
    jobs = load_jobs(jobs_queue_file)
    for job in jobs:
        if job['status'] == 'executing':
            job['status'] = 'pending'
            custom_print(f"{RED}A probable crash or aborted job execution was detected from your last use.... checking on status of unfinished jobs..{ENDC}\n\n")
            if isinstance(job['sourcecache'], list):
                source_basenames = [os.path.basename(path) for path in job['sourcecache']]
            else:
                source_basenames = os.path.basename(job['sourcecache'])

                custom_print(f"{GREEN}A job {GREEN}{source_basenames}{ENDC} to -> {GREEN}{os.path.basename(job['targetcache'])} was found that terminated early it will be moved back to the pending jobs queue - you have a Total of {PENDING_JOBS_COUNT + JOB_IS_RUNNING} in the Queue\n\n")
            save_jobs(jobs_queue_file, jobs)
    if not keep_completed_jobs:
        jobs = [job for job in jobs if job['status'] != 'completed']
        save_jobs(jobs_queue_file, jobs)
        custom_print(f"{BLUE}All completed jobs have been removed, if you would like to keep completed jobs change the setting to True{ENDC}\n\n")

def copy_to_media_cache(file_paths):
    if isinstance(file_paths, str):
        file_paths = [file_paths]  # Convert single file path to list
    cached_paths = []
    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        base_name, ext = os.path.splitext(file_name)
        counter = 0
        while True:
            new_name = f"{base_name}_{counter}{ext}" if counter > 0 else file_name
            cache_path = os.path.join(media_cache_dir, new_name)
            if not os.path.exists(cache_path):
                shutil.copy(file_path, cache_path)
                cached_paths.append(cache_path)
                break
            else:
                cache_size = os.path.getsize(cache_path)
                if file_size == cache_size:
                    cached_paths.append(cache_path)  # If size matches, assume it's the same file
                    break
            counter += 1

    # Ensure target_path is treated as a single path
    if isinstance(cached_paths, list) and len(cached_paths) == 1:
        return cached_paths[0]  # Return the single path
    else:
        return cached_paths  # Return the list of paths

def check_for_unneeded_media_cache():
    # List all files in the media cache directory
    cache_files = os.listdir(media_cache_dir)
    jobs = load_jobs(jobs_queue_file)
    # Create a set to store all needed filenames from the jobs
    needed_files = set()
    for job in jobs:
        if job['status'] in {'pending', 'failed', 'missing', 'editing', 'executing'}:
            source_basename = os.path.basename(job['sourcecache'])
            target_basename = os.path.basename(job['targetcache'])
            needed_files.add(source_basename)
            needed_files.add(target_basename)
    # Delete files that are not needed
    for cache_file in cache_files:
        if cache_file not in needed_files:
            os.remove(os.path.join(media_cache_dir, cache_file))
            custom_print(f"{GREEN}Deleted unneeded file: {cache_file}{ENDC}")

def check_if_needed(job, source_or_target):
    with open(jobs_queue_file, 'r') as file:
        jobs = json.load(file)

    relevant_statuses = {'pending', 'executing', 'failed', 'missing', 'editing', 'archived'}
    file_usage_counts = {}

    # Create an index list for all jobs with relevant statuses and count file paths
    for other_job in jobs:
        if other_job['status'] in relevant_statuses:
            for key in ['sourcecache', 'targetcache']:
                paths = other_job[key] if isinstance(other_job[key], list) else [other_job[key]]
                for path in paths:
                    normalized_path = os.path.normpath(path)
                    file_usage_counts[normalized_path] = file_usage_counts.get(normalized_path, 0) + 1

    # Check and handle sourcecache paths
    if source_or_target in ['both', 'source']:
        source_paths = job['sourcecache'] if isinstance(job['sourcecache'], list) else [job['sourcecache']]
        for source_path in source_paths:
            normalized_source_path = os.path.normpath(source_path)
            if file_usage_counts.get(normalized_source_path, 0) < 2:
                if os.path.exists(normalized_source_path):
                    try:
                        os.remove(normalized_source_path)
                        custom_print(f"Successfully deleted the file: {GREEN}{os.path.basename(normalized_source_path)}{ENDC} as it is no longer needed by any other jobs\n\n")
                    except Exception as e:
                        custom_print(f"{RED}Failed to delete {YELLOW}{os.path.basename(normalized_source_path)}{ENDC}: {e}\n\n")
                else:
                    custom_print(f"{BLUE}No need to delete the file: {GREEN}{os.path.basename(normalized_source_path)}{ENDC} as it does not exist.\n\n")
            else:
                custom_print(f"{BLUE}Did not delete the file: {GREEN}{os.path.basename(normalized_source_path)}{ENDC} as it's needed by another job.\n\n")

    # Check and handle targetcache path
    if source_or_target in ['both', 'target']:
        target_cache_path = job['targetcache']
        if isinstance(target_cache_path, list):
            target_cache_path = target_cache_path[0]  # Assuming the first element if it's erroneously a list
        normalized_target_path = os.path.normpath(target_cache_path)
        if file_usage_counts.get(normalized_target_path, 0) < 2:
            if os.path.exists(normalized_target_path):
                try:
                    os.remove(normalized_target_path)
                    custom_print(f"Successfully deleted the file: {GREEN}{os.path.basename(normalized_target_path)}{ENDC} as it is no longer needed by any other jobs\n\n")
                except Exception as e:
                    custom_print(f"{RED}Failed to delete {YELLOW}{os.path.basename(normalized_target_path)}{ENDC}: {e}\n\n")
            else:
                custom_print(f"{BLUE}No need to delete the file: {GREEN}{os.path.basename(normalized_target_path)}{ENDC} as it does not exist.\n\n")
        else:
            custom_print(f"{BLUE}Did not delete the file: {GREEN}{os.path.basename(normalized_target_path)}{ENDC} as it's needed by another job.\n\n")

def render() -> gradio.Blocks:
    global ADD_JOB_BUTTON, RUN_JOBS_BUTTON, status_window
    with gradio.Blocks() as layout:
        with gradio.Row():
            with gradio.Column(scale = 2):
                with gradio.Blocks():
                    about.render()
                with gradio.Blocks():
                    frame_processors.render()
                with gradio.Blocks():
                    frame_processors_options.render()
                with gradio.Blocks():
                    execution.render()
                    execution_thread_count.render()
                    execution_queue_count.render()
                with gradio.Blocks():
                    memory.render()
                with gradio.Blocks():
                    temp_frame.render()
                with gradio.Blocks():
                    output_options.render()
            with gradio.Column(scale = 2):
                with gradio.Blocks():
                    source.render()
                with gradio.Blocks():
                    target.render()
                with gradio.Blocks():
                    output.render()
                # with gradio.Blocks():
                    # status_window.render()
                with gradio.Blocks():
                    ADD_JOB_BUTTON.render()
                with gradio.Blocks():
                    RUN_JOBS_BUTTON.render()
                with gradio.Blocks():
                    EDIT_JOB_BUTTON.render()
            with gradio.Column(scale = 3):
                with gradio.Blocks():
                    preview.render()
                with gradio.Blocks():
                    trim_frame.render()
                with gradio.Blocks():
                    face_selector.render()
                with gradio.Blocks():
                    face_masker.render()
                with gradio.Blocks():
                    face_analyser.render()
                with gradio.Blocks():
                    common_options.render()
    return layout

    

def listen() -> None:
    global EDIT_JOB_BUTTON, status_window
    ADD_JOB_BUTTON.click(assemble_queue)
    RUN_JOBS_BUTTON.click(execute_jobs)
    EDIT_JOB_BUTTON.click(edit_queue)
    # status_window.change(custom_print, inputs=[], outputs=[status_window])
    frame_processors.listen()
    frame_processors_options.listen()
    execution.listen()
    execution_thread_count.listen()
    execution_queue_count.listen()
    memory.listen()
    temp_frame.listen()
    output_options.listen()
    source.listen()
    target.listen()
    output.listen()
    preview.listen()
    trim_frame.listen()
    face_selector.listen()
    face_masker.listen()
    face_analyser.listen()
    common_options.listen()

# def load_validate_args(job):
    # before_values = get_values_from_globals("before_load_validate_args")
    # setup_globals_from_job_args(job)
    # program = ArgumentParser()
    # program.set_defaults(**job)
    # core.validate_args(program)
    # after_values = get_values_from_globals("after_load_validate_args")
    
# def load_apply_args(job):
    # before_values = get_values_from_globals("before_load_apply_args")
    # setup_globals_from_job_args(job)
    # program = ArgumentParser()
    # program.set_defaults(**job)
    # core.apply_args(program)
    # after_values = get_values_from_globals("after_load_apply_args")



# def edit_command(job):   #figure it out how tol load it back to webui without executing
    # # Setup global variables from job arguments
    # setup_globals_from_job_args(job)
    # program = ArgumentParser()
    # program.set_defaults(**job)
    # core.validate_args(program)
    # core.apply_args(program)
    # subprocess.Popen(
            # "python facefusion\\uis\\layouts\\QueueItUp.py", 
            # shell=True, 
            # stdout=subprocess.PIPE, 
            # stderr=subprocess.STDOUT, 
            # text=True, 
            # bufsize=1
        # ) 
    # #core.run(program)
    # #core.conditional_process()



def run_job_args(job): ###figure out if core.run is correct
    before_values = get_values_from_globals("before_job_command")
    setup_globals_from_job_args(job)
    program = ArgumentParser()
    program.set_defaults(**job)
    core.validate_args(program)
    core.run(program)
    #core.conditional_process()
    after_values = get_values_from_globals("after_job_command")

def assemble_queue():
    global RUN_JOBS_BUTTON, ADD_JOB_BUTTON, jobs_queue_file
    # default_values are already initialized, do not call for new default values
    job_args = get_values_from_globals('job_args')
    current_values = get_values_from_globals('current_values')

    if "execution_providers" in job_args:
        new_providers = []
        for provider in job_args["execution_providers"]:
            if provider == "CUDAExecutionProvider":
                new_providers.append('cuda')
            elif provider == "CPUExecutionProvider":
                new_providers.append('cpu')
            elif provider == "CoreMLExecutionProvider":
                new_providers.append('coreml')
            else:
                new_providers.append(provider)
        job_args["execution_providers"] = new_providers
    source_paths = current_values.get("source_paths", [])
    target_path = current_values.get("target_path", "")
    output_path = current_values.get("output_path", "")

    while True:
        if JOB_IS_RUNNING:
            if JOB_IS_EXECUTING:
                custom_print("Job is executing.")
                break  # Exit the loop if the job is executing
            else:
                custom_print("Job is running but not executing. Stuck in loop.\n")
                time.sleep(1)  # Wait for 1 second to reduce CPU usage, continue checking
        else:
            custom_print("Job is not running.")
            break  # Exit the loop if the job is not running

    oldeditjob = None
    found_editing = False
    jobs = load_jobs(jobs_queue_file)

    for job in jobs:
        if job['status'] == 'editing':
            oldeditjob = job.copy()  
            found_editing = True
            break

    cache_source_paths = copy_to_media_cache(source_paths)
    source_basenames = [os.path.basename(path) for path in cache_source_paths] if isinstance(cache_source_paths, list) else os.path.basename(cache_source_paths)
    custom_print(f"{GREEN}Source file{ENDC} copied to Media Cache folder: {GREEN}{source_basenames}{ENDC}\n\n")
    cache_target_path = copy_to_media_cache(target_path)
    custom_print(f"{GREEN}Target file{ENDC} copied to Media Cache folder: {GREEN}{os.path.basename(cache_target_path)}{ENDC}\n\n")
    
    if isinstance(cache_source_paths, str):
        cache_source_paths = [cache_source_paths]  # Convert to list if it's a single string

    job_args['source_paths'] = cache_source_paths
    job_args['target_path'] = cache_target_path
    job_args['headless'] = 'None'
    current_values['source_paths'] = cache_source_paths
    current_values['target_path'] = cache_target_path
    
    new_job = {
        "job_args": job_args,
        "status": "pending",
        "sourcecache": (cache_source_paths),
        "targetcache": (cache_target_path),
        "output_path": (output_path),
    }
    if debugging:
        with open(os.path.join(working_dir, f"job_args.txt"), "w") as file:
            for key, val in job_args.items():
                file.write(f"{key}: {val}\n")

                
                
        custom_print("job_args.txt re-created")
    if debugging:
        with open(os.path.join(working_dir, f"current_values.txt"), "w") as file:
            for key, val in current_values.items():
                file.write(f"{key}: {val}\n")
        custom_print("current_values.txt re-created")
        
    if found_editing:
        if not (oldeditjob['sourcecache'] == new_job['sourcecache'] or oldeditjob['sourcecache'] == new_job['targetcache']):
            check_if_needed(oldeditjob, 'source')
        if not (oldeditjob['targetcache'] == new_job['sourcecache'] or oldeditjob['targetcache'] == new_job['targetcache']):
            check_if_needed(oldeditjob, 'target')

        job.update(new_job)
        save_jobs(jobs_queue_file, jobs)
        custom_print(f"{GREEN}You have successfully returned the Edited job back to the job Queue, it is now a Pending Job {ENDC}")



    if not found_editing:
        jobs.append(new_job)
        save_jobs(jobs_queue_file, jobs)
    count_existing_jobs()

    if JOB_IS_RUNNING:
        custom_print(f"{BLUE}job # {CURRENT_JOB_NUMBER + PENDING_JOBS_COUNT} was added {ENDC} - and is in line to be Processed - Click Add Job to Queue more Jobs")
    else:
        custom_print(f"{BLUE}Your Job was Added to the queue,{ENDC} there are a total of {GREEN}#{PENDING_JOBS_COUNT} Job(s){ENDC} in the queue,  Add More Jobs, Edit the Queue, or Click Run Queue to Execute all the queued jobs")

    
# def multiprocess_execute_jobs():
    # # Start the job command as a process with the given job arguments
    # job_process = Process(target=execute_jobs)
    # job_process.start()
    # job_process.join()  # Optional: wait for the process to complete

def execute_jobs():
    global JOB_IS_RUNNING, JOB_IS_EXECUTING,CURRENT_JOB_NUMBER,jobs_queue_file
    count_existing_jobs()
    if not PENDING_JOBS_COUNT + JOB_IS_RUNNING > 0:
        custom_print(f"Whoops!!!, There are {PENDING_JOBS_COUNT} Job(s) queued.  Add a job to the queue before pressing Run Queue.\n\n")
        

    if PENDING_JOBS_COUNT + JOB_IS_RUNNING > 0 and JOB_IS_RUNNING:
        custom_print(f"Whoops a Jobs is already executing, with {PENDING_JOBS_COUNT} more job(s) waiting to be processed.\n\n You don't want more then one job running at the same time your GPU cant handle that,\n\nYou just need to click add job if jobs are already running, and thie job will be placed in line for execution. you can edit the job order with Edit Queue button\n\n")

    jobs = load_jobs(jobs_queue_file)
    JOB_IS_RUNNING = 1
    CURRENT_JOB_NUMBER = 0
    current_run_job = {}
    first_pending_job = next((job for job in jobs if job['status'] == 'pending'), None)
    # Remove the first pending job from jobs by keeping jobs that are not the first_pending_job
    jobs = [job for job in jobs if job != first_pending_job]
    # Change status to 'executing' and add it back to the jobs
    first_pending_job['status'] = 'executing'
    jobs.append(first_pending_job)
    save_jobs(jobs_queue_file, jobs)

    while True:
        if not first_pending_job['status'] == 'executing':
            break
        current_run_job = first_pending_job
        count_existing_jobs()
        JOB_IS_EXECUTING = 1
        CURRENT_JOB_NUMBER += 1
        custom_print(f"{PENDING_JOBS_COUNT} jobs remaining:{ENDC}\n\n\n\n")
        custom_print(f"{BLUE}Starting Job #{GREEN} {CURRENT_JOB_NUMBER}{ENDC}\n\n")

        printjobtype = current_run_job['job_args']['frame_processors']
        custom_print(f"{BLUE}Executing Job # {CURRENT_JOB_NUMBER} of {CURRENT_JOB_NUMBER + PENDING_JOBS_COUNT}  {ENDC} - {YELLOW}{printjobtype}\n\n")

        if isinstance(current_run_job['sourcecache'], list):
            source_basenames = [os.path.basename(path) for path in current_run_job['sourcecache']]
        else:
            source_basenames = os.path.basename(current_run_job['sourcecache'])

        custom_print(f"Job #{CURRENT_JOB_NUMBER} will be SWAPPING - {GREEN}{source_basenames}{ENDC} to -> {GREEN}{os.path.basename(current_run_job['targetcache'])}{ENDC}\n\n")

        run_job_args(current_run_job['job_args'])

        JOB_IS_EXECUTING = 0  # Reset the job execution flag
        
        custom_print(f"{BLUE}Job {CURRENT_JOB_NUMBER} completed pausing 5 seconds.{ENDC}\n")



        
        ### fix this so status isnt always completed

        current_run_job['status'] = 'completed'
        time.sleep(5)

        
        if current_run_job['status'] == 'completed':
            custom_print(f"{BLUE}Job {CURRENT_JOB_NUMBER} completed successfully.{ENDC}\n")
        else: 
            current_run_job['status'] = 'failed'
            if isinstance(current_run_job['sourcecache'], list):
                source_basenames = [os.path.basename(path) for path in current_run_job['sourcecache']]
            else:
                source_basenames = os.path.basename(current_run_job['sourcecache'])
            custom_print(f"{RED}Job {CURRENT_JOB_NUMBER} failed.{ENDC} Please check the validity of {RED}{source_basenames}{ENDC} and {RED}{os.path.basename(current_run_job['targetcache'])}.{ENDC}")
        jobs = load_jobs(jobs_queue_file)
        jobs = [job for job in jobs if job['status'] != 'executing']
        jobs.append(current_run_job)
        save_jobs(jobs_queue_file, jobs)
 
        # Reset current_run_job to None, indicating it's no longer holding a job
        current_run_job = None
        # Find the first pending job
        jobs = load_jobs(jobs_queue_file)
        
        first_pending_job = next((job for job in jobs if job['status'] == 'pending'), None)
        
        if first_pending_job:
            jobs = [job for job in jobs if job != first_pending_job]
            current_run_job = first_pending_job.copy()
            current_run_job['status'] = 'executing'
            jobs.append(current_run_job)
            first_pending_job = current_run_job
            save_jobs(jobs_queue_file, jobs)
        else:#no more pending jobs
            custom_print(f"{BLUE}a total of {CURRENT_JOB_NUMBER} Jobs have completed processing,{ENDC}...... {GREEN}the Queue is now empty, {BLUE}Feel Free to QueueItUp some more..{ENDC}")
            current_run_job = None
            first_pending_job = None
            break
    JOB_IS_RUNNING = 0
    save_jobs(jobs_queue_file, jobs)
    check_for_unneeded_media_cache()


def edit_queue():
    global root, frame, output_text, jobs_queue_file
    EDIT_JOB_BUTTON = gradio.Button("Edit Queue")
    jobs = load_jobs(jobs_queue_file)  
    root = tkinter.Tk()
    root.geometry('1200x800')
    root.title("Edit Queued Jobs")
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    # output_text = Text(root, height=10, width=100)
    # output_text.pack()
    # output_text.insert(tkinter.END, "Initialization successful\n") 
    # output_text.tag_configure('red', foreground='red')
    # output_text.tag_configure('green', foreground='green')
    # output_text.tag_configure('yellow', foreground='yellow')
    # output_text.tag_configure('blue', foreground='blue')
    #scrollbar = Scrollbar(root, command=output_text.yview)
    scrollbar = Scrollbar(root)
    scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)
    canvas = tkinter.Canvas(root, scrollregion=(0, 0, 0, 7000))
    canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
    frame = Frame(canvas)
    canvas.create_window((0, 0), window=frame, anchor='nw')
    #output_text.config(yscrollcommand=scrollbar.set)
    canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)), "units"))
    custom_font = font.Font(family="Helvetica", size=12, weight="bold")
    bold_font = font.Font(family="Helvetica", size=12, weight="bold")
    
    close_button = tkinter.Button(root, text="Close Window", command=root.destroy, font=custom_font)
    close_button.pack(pady=5)

    refresh_button = tkinter.Button(root, text="Refresh View", command=lambda: refresh_frame_listbox(), font=custom_font)
    refresh_button.pack(pady=5)

    # run_jobs_button = tkinter.Button(root, text=f"RUN {PENDING_JOBS_COUNT} JOBS", command=lambda: check_and_run_jobs(), font=custom_font)
    # run_jobs_button.pack(pady=5)


    pending_jobs_button = tkinter.Button(root, text=f"Delete {PENDING_JOBS_COUNT} Pending Jobs", command=lambda: delete_pending_jobs(), font=custom_font)
    pending_jobs_button.pack(pady=5)
    
    missing_jobs_button = tkinter.Button(root, text="Delete Missing ", command=lambda: delete_missing_media_jobs(), font=custom_font)
    missing_jobs_button.pack(pady=5)
    
    archived_jobs_button = tkinter.Button(root, text="Delete archived ", command=lambda: delete_archived_jobs(), font=custom_font)
    archived_jobs_button.pack(pady=5)
    
    

    failed_jobs_button = tkinter.Button(root, text="Delete Failed", command=lambda: delete_failed_jobs(), font=custom_font)
    failed_jobs_button.pack(pady=5)

    completed_jobs_button = tkinter.Button(root, text="Delete Completed", command=lambda: delete_completed_jobs(), font=custom_font)
    completed_jobs_button.pack(pady=5)
               

    def refresh_frame_listbox():
        global jobs # Ensure we are modifying the global list
        status_priority = {'editing': 0, 'executing': 1, 'pending': 2, 'failed': 3, 'missing': 4, 'completed': 5, 'archived': 6}
        jobs = load_jobs(jobs_queue_file)

        # # First, sort the entire list by status priority
        jobs.sort(key=lambda x: status_priority.get(x['status'], 6))

        # Save the newly sorted list back to the file
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        # root.destroy()
        # edit_queue()
    
    def close_window():
        root.destroy()
        save_jobs(jobs_queue_file, jobs)

    def delete_pending_jobs():
        jobs = load_jobs(jobs_queue_file)
        jobs = [job for job in jobs if job['status'] != 'pending']
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()
        
    def delete_completed_jobs():
        jobs = load_jobs(jobs_queue_file)
        jobs = [job for job in jobs if job['status'] != 'completed']
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

    def delete_failed_jobs():
        jobs = load_jobs(jobs_queue_file)
        jobs = [job for job in jobs if job['status'] != 'failed']        
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

        
    def delete_missing_media_jobs(): 
        jobs = load_jobs(jobs_queue_file)
        jobs = [job for job in jobs if job['status'] != 'missing']
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

    def archive_job(job, source_or_target):
        # Update the job status to 'archived'
        job['status'] = 'archived'
        save_jobs(jobs_queue_file, jobs) 
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

    def delete_archived_jobs(): 
        jobs = load_jobs(jobs_queue_file)
        # Loop through jobs and process archived jobs
        for job in jobs:
            if job['status'] == 'archived':
                check_if_needed(job, 'both')
        # Filter out jobs with the status 'archived'
        jobs = [job for job in jobs if job['status'] != 'archived']
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

    def reload_job_in_facefusion_edit(job):
        # Check if sourcecache and targetcache files exist
        sourcecache_path = job.get('sourcecache')
        targetcache_path = job.get('targetcache')

        # Handling multiple sourcecache paths
        if isinstance(sourcecache_path, list):
            missing_files = [path for path in sourcecache_path if not os.path.exists(path)]
            if missing_files:
                messagebox.showerror("Error", f"Cannot edit job. The following source files do not exist: {', '.join(os.path.basename(path) for path in missing_files)}")
                return
        else:
            if not os.path.exists(sourcecache_path):
                messagebox.showerror("Error", f"Cannot edit job. The source file '{os.path.basename(sourcecache_path)}' does not exist.")
                return

        # Checking single targetcache path
        if not os.path.exists(targetcache_path):
            messagebox.showerror("Error", f"Cannot edit job. The target file '{os.path.basename(targetcache_path)}' does not exist.")
            return

        # Confirmation dialog before editing the job
        response = messagebox.askyesno("Confirm Edit", "THIS WILL REMOVE THIS PENDING JOB FROM THE QUEUE, AND LOAD IT INTO FACEFUSION WEBUI FOR EDITING, WHEN DONE EDITING CLICK START TO RUN IT OR ADD JOB TO REQUEUE IT. ARE YOU SURE YOU WANT TO EDIT THIS JOB", icon='warning')
        if not response:
            # If user clicks 'No', exit the function
            return

        
        job['status'] = 'editing'
        # job['job_args']['headless'] = 'None'
        # print(job['status'])
        # save_jobs(jobs_queue_file, jobs)
        # update_job_listbox()
        # custom_print(job['status'])
        # edit_command(job['job_args'])
        
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()
        print (job['status'])

        top = Toplevel()
        top.title("Please Wait")
        message_label = tkinter.Label(top, text="Please wait while the job loads back into FaceFusion...", padx=20, pady=20)
        message_label.pack()
        print (job['status'])
        if isinstance(job['sourcecache'], list):
            arg_source_paths = ' '.join(f'-s "{p}"' for p in job['sourcecache'])
        else:
            arg_source_paths = f"-s \"{job['sourcecache']}\""

        python_cmd = f"python run.py {arg_source_paths} -t \"{job['targetcache']}\" -o \"{job['output_path']}\" --ui-layouts QueueItUp"
        print(python_cmd)
        subprocess.Popen(python_cmd)

        top.after(1000, close_window)
        top.update_idletasks()
        x = (top.winfo_screenwidth() // 2) - (top.winfo_reqwidth() // 2)
        y = (top.winfo_screenheight() // 2) - (top.winfo_reqheight() // 2)
        top.geometry("+{}+{}".format(x, y))
        top.after(7000, top.destroy)

    def output_path_job(job):
        # Open a dialog to select a directory
        selected_path = askdirectory(title="Select A New Output Path for this Job")
        if selected_path:
            formatted_path = selected_path.replace('/', '\\')  # Replace single forward slashes with backslashes
            job['output_path'] = formatted_path
            update_paths(job,'output', formatted_path)
        save_jobs(jobs_queue_file, jobs)  # Save the updated jobs to the JSON file
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()

    def delete_job(job, source_or_target):
        job['status'] = ('deleting')
        source_or_target='both'
        check_if_needed(job, 'both')
        jobs.remove(job)
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()  # Refresh the job list to show the new thumbnail or placeholder
        refresh_frame_listbox()


    def move_job_up(index):
        if index > 0:
            jobs.insert(index - 1, jobs.pop(index))
            save_jobs(jobs_queue_file, jobs)
            update_job_listbox()

    def move_job_down(index):
        if index < len(jobs) - 1:
            jobs.insert(index + 1, jobs.pop(index))
            save_jobs(jobs_queue_file, jobs)
            update_job_listbox()

    def move_job_to_top(index):
        if index > 0:
            jobs.insert(0, jobs.pop(index))
            save_jobs(jobs_queue_file, jobs)
            update_job_listbox()

    def move_job_to_bottom(index):
        if index < len(jobs) - 1:
            jobs.append(jobs.pop(index))
            save_jobs(jobs_queue_file, jobs)
            update_job_listbox()
            
    def create_job_thumbnail(parent, job, source_or_target):
        print("create_job_thumbnail called")
        button = None
        file_paths = job[source_or_target + 'cache']
        file_paths = file_paths if isinstance(file_paths, list) else [file_paths]

        # Ensure thumbnail directory exists
        if not os.path.exists(thumbnail_dir):
            os.makedirs(thumbnail_dir)

        num_images = len(file_paths)
        grid_size = math.ceil(math.sqrt(num_images))  # Number of rows and columns
        thumb_size = 200 // grid_size  # Size of each thumbnail to fit the grid

        print(f"Grid size: {grid_size}x{grid_size}, Thumbnail size: {thumb_size}x{thumb_size}")

        thumbnail_files = []
        for idx, file_path in enumerate(file_paths):
            thumbnail_path = os.path.join(thumbnail_dir, f"{source_or_target}_thumb_{idx}.png")
            if file_path.lower().endswith(('.mp3', '.wav', '.aac', '.flac')):
                audio_icon_path = os.path.join(working_dir, 'audioicon.png')
                cmd = [
                    'ffmpeg', '-i', audio_icon_path,
                    '-vf', f'scale={thumb_size}:{thumb_size}',
                    '-vframes', '1',
                    '-y', thumbnail_path
                ]
            else:
                cmd = [
                    'ffmpeg', '-i', file_path,
                    '-vf', f'scale={thumb_size}:{thumb_size}',
                    '-vframes', '1',
                    '-y', thumbnail_path
                ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            thumbnail_files.append(thumbnail_path)

        list_file_path = os.path.join(thumbnail_dir, 'input_list.txt')
        with open(list_file_path, 'w') as file:
            for thumb in thumbnail_files:
                file.write(f"file '{thumb}'\n")

        grid_path = os.path.join(thumbnail_dir, f"{source_or_target}_grid.png")
        grid_cmd = [
            'ffmpeg',
            '-loglevel', 'error',
            '-f', 'concat', '-safe', '0', '-i', list_file_path,
            '-filter_complex', f'tile={grid_size}x{grid_size}:padding=2',
            '-y', grid_path
        ]
        grid_result = subprocess.run(grid_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if grid_result.returncode != 0:
            print(f"Error creating grid: {grid_result.stderr.decode()}")
            return None

        try:
            with open(grid_path, 'rb') as f:
                grid_image_data = BytesIO(f.read())
            grid_photo_image = PhotoImage(data=grid_image_data.read())
            button = Button(parent, image=grid_photo_image, command=lambda ft=source_or_target: select_job_file(parent, job, ft))
            button.image = grid_photo_image  # keep a reference!
            button.pack(side='left', padx=5)
        except Exception as e:
            print(f"Failed to open grid image: {e}")
            
        # Clean up thumbnail directory
        # for file in os.listdir(thumbnail_dir):
            # os.remove(os.path.join(thumbnail_dir, file))
        return button





    def edit_arguments_text(job):
        edit_window = tkinter.Toplevel()
        edit_window.title("Edit Job Arguments")
        edit_window.geometry("600x400")

        canvas = tkinter.Canvas(edit_window)
        scrollbar = tkinter.Scrollbar(edit_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tkinter.Frame(canvas)

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)), "units"))
        entries = {}

        excluded_keys = {
            "FACE_MASK_REGION_GROUP", "MODELS", "PROBABILITY_LIMIT", "PROCESS_STATE",
            "RATE_LIMIT", "STREAM_COUNTER", "VOICE_EXTRACTOR", "execution_providers",
            "face_debugger_items", "face_mask_padding", "face_mask_regions",
            "face_recognizer_model", "video_template_sizes", "ui_layouts", "force_download", "image_template_sizes"
        }

        def add_entry(key, value, parent_frame):
            if key in excluded_keys:
                return

            frame = tkinter.Frame(parent_frame)
            frame.pack(fill='x', expand=True)

            label = tkinter.Label(frame, text=str(key) + ":")
            label.pack(side='left', padx=5)

            if isinstance(value, list):
                entry_frame = tkinter.Frame(frame)
                entry_frame.pack(side='right', fill='x', expand=True)
                entry = tkinter.Entry(entry_frame, width=50)
                entry.insert(0, ", ".join(str(x) for x in value))
                entry.pack(fill='x', expand=True)
                entries[key] = entry
            else:
                entry = tkinter.Entry(frame)
                entry.insert(0, str(value))
                entry.pack(side='right', fill='x', expand=True)
                entries[key] = entry

        for key, value in job['job_args'].items():
            add_entry(key, value, scrollable_frame)

        def save_changes():
            for key, entry in entries.items():
                if isinstance(job['job_args'][key], list):
                    job['job_args'][key] = [x.strip() for x in entry.get().split(',')]
                else:
                    job['job_args'][key] = entry.get()
            edit_window.destroy()

        ok_button = tkinter.Button(edit_window, text="OK", command=save_changes)
        ok_button.pack(pady=5)

        cancel_button = tkinter.Button(edit_window, text="Cancel", command=edit_window.destroy)
        cancel_button.pack(pady=5)

        # Ensure the scroll region is updated
        scrollable_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        edit_window.mainloop()

        
    def select_job_file(parent, job, source_or_target):
        # Determine the allowed file types based on the source_or_target and current file extension
        file_types = []
        if source_or_target == 'source':
            file_types = [('source files', '*.jpg *.jpeg *.png *.mp3 *.wav *.aac')]
        elif source_or_target == 'target':
            # Get current extension
            current_extension = job['targetcache'].lower().rsplit('.', 1)[-1]
            if current_extension in ['jpg', 'jpeg', 'png']:
                file_types = [('Image files', '*.jpg *.jpeg *.png')]
            elif current_extension in ['mp4', 'mov', 'avi', 'mkv']:
                file_types = [('Video files', '*.mp4 *.avi *.mov *.mkv')]

        # Open file dialog with the appropriate filters
        if source_or_target == 'source':
            selected_paths = filedialog.askopenfilenames(title=f"Select {source_or_target.capitalize()} File(s)", filetypes=file_types)
        else:
            selected_path = filedialog.askopenfilename(title=f"Select {source_or_target.capitalize()} File", filetypes=file_types)
            selected_paths = [selected_path] if selected_path else []


        if selected_paths:
            check_if_needed(job, source_or_target)
            # Update job command with the selected path(s)
            update_paths(job, source_or_target, selected_paths)

            # Check if all source cache files exist
            if isinstance(job['sourcecache'], list):
                source_cache_exists = all(os.path.exists(cache) for cache in job['sourcecache'])
            else:
                source_cache_exists = os.path.exists(job['sourcecache'])
            # job['status'] = 'checking'
            
            
            if source_cache_exists and os.path.exists(job['targetcache']):
                job['status'] = 'pending'
            else:
                job['status'] = 'missing'
     
            save_jobs(jobs_queue_file, jobs)
            update_job_listbox()

    def update_paths(job, source_or_target_or_output, path):
        custom_print(f"source_or_target_or_output : {source_or_target_or_output}")

        if source_or_target_or_output == 'source':
            cache_path = copy_to_media_cache(path)
            if not isinstance(cache_path, list):
                cache_path = [cache_path]  # Ensure cache_path is a list
            path_key = 'source_paths'
            cache_key = 'sourcecache'
            job[cache_key] = cache_path


        if source_or_target_or_output == 'target':
            cache_path = copy_to_media_cache(path)
            path_key = 'target_path'
            cache_key = 'targetcache'
            job[cache_key] = cache_path
            
        if source_or_target_or_output == 'output':
            path_key = 'output_path'
            cache_key = 'output_path'
            cache_path = job['output_path']   
            
        job['job_args'][path_key] = cache_path
        save_jobs(jobs_queue_file, jobs)
        update_job_listbox()

    def update_job_listbox():
        global image_references
        count_existing_jobs()
        image_references.clear()
        for widget in frame.winfo_children():
            widget.destroy()

        for index, job in enumerate(jobs):
            # Ensure sourcecache is always a list for consistency
            source_paths = job['sourcecache'] if isinstance(job['sourcecache'], list) else [job['sourcecache']]
            source_thumb_exists = all(os.path.exists(os.path.normpath(source)) for source in source_paths)

            # Ensure targetcache is treated as a single path
            target_cache_path = job['targetcache'] if isinstance(job['targetcache'], str) else job['targetcache'][0]
            target_thumb_exists = os.path.exists(os.path.normpath(target_cache_path))

            bg_color = 'SystemButtonFace'  # Default color
            if job['status'] == 'failed':
                bg_color = 'red'
            if job['status'] == 'executing':
                bg_color = 'black'
            if job['status'] == 'completed':
                bg_color = 'grey'
            if job['status'] == 'editing':
                bg_color = 'green'

            if job['status'] == 'pending':
                bg_color = 'SystemButtonFace'
            if not source_thumb_exists or not target_thumb_exists:
                bg_color = 'red'  # Highlight missing files in red
            if job['status'] == 'archived':
                bg_color = 'brown'
            # Create job frame with updated background color
            job_frame = tkinter.Frame(frame, borderwidth=2, relief='groove', background=bg_color)
            job_frame.pack(fill='x', expand=True, padx=5, pady=5)

            # Move job frame for the move buttons
            move_job_frame = tkinter.Frame(job_frame)
            move_job_frame.pack(side='left', fill='x', padx=5)
            # Move up button
            move_top_button = tkinter.Button(move_job_frame, text="   Top   ", command=lambda idx=index: move_job_to_top(idx))
            move_top_button.pack(side='top', fill='y')
            move_up_button = tkinter.Button(move_job_frame, text="   Up   ", command=lambda idx=index: move_job_up(idx))
            move_up_button.pack(side='top', fill='y')
            # Move down button
            move_down_button = tkinter.Button(move_job_frame, text=" Down ", command=lambda idx=index: move_job_down(idx))
            move_down_button.pack(side='top', fill='y')
            # Move bottom button
            move_bottom_button = tkinter.Button(move_job_frame, text="Bottom", command=lambda idx=index: move_job_to_bottom(idx))
            move_bottom_button.pack(side='top', fill='y')
            
            source_frame = tkinter.Frame(job_frame)
            source_frame.pack(side='left', fill='x', padx=5)
            source_button = create_job_thumbnail(job_frame, job, 'source')
            if source_button:
                source_button.pack(side='left', padx=5)
            else:
                print("Failed to create source button.")

            # Frame to hold the arrow label and archive button
            action_archive_frame = tkinter.Frame(job_frame)
            action_archive_frame.pack(side='left', fill='x', padx=5)
            

            arrow_label = Label(action_archive_frame, text=f"{job['status']}\n\u27A1", font=bold_font)
            arrow_label.pack(side='top', padx=5)
            
            output_path_button = tkinter.Button(action_archive_frame, text="Output Path", command=lambda j=job: output_path_job(j))
            output_path_button.pack(side='top', padx=2)
                        
            delete_button = tkinter.Button(action_archive_frame, text=" Delete ", command=lambda j=job: delete_job(j, 'both'))
            delete_button.pack(side='top', padx=2)
            archive_button = tkinter.Button(action_archive_frame, text="Archive",command=lambda j=job: archive_job(j, 'both'))
            archive_button.pack(side='top', padx=2)
            
            # test_job_command_button = tkinter.Button(action_archive_frame, text="run_job_args",command=lambda j=job: test_run_job_command(j))
            # test_job_command_button.pack(side='top', padx=2)

            # test_apply_args_button = tkinter.Button(action_archive_frame, text="apply_args",command=lambda j=job: test_apply_args(j))
            # test_apply_args_button.pack(side='top', padx=2)

            # test_validate_args_button = tkinter.Button(action_archive_frame, text="validate_args",command=lambda j=job: test_validate_args(j))
            # test_validate_args_button.pack(side='top', padx=2)

            target_frame = tkinter.Frame(job_frame)
            target_frame.pack(side='left', fill='x', padx=5)
            target_button = create_job_thumbnail(job_frame, job, 'target')
            if target_button:
                target_button.pack(side='left', padx=5)
            else:
                print("Failed to create target button.")
    

            # frame for the Command Arguments
            argument_frame = tkinter.Frame(job_frame)
            argument_frame.pack(side='left', fill='x', padx=5)

            custom_font = font.Font(family="Helvetica", size=12, weight="bold")
            facefusion_button = tkinter.Button(argument_frame, text=f"UN-Queue It Up\n\n --EDIT ARGUMENTS", font=bold_font, justify='center')
            facefusion_button.pack(side='top', padx=5, fill='x', expand=False)
            facefusion_button.bind("<Button-1>", lambda event, j=job: reload_job_in_facefusion_edit(j))


            custom_font = font.Font(family="Helvetica", size=10, weight="bold")
            argument_button = tkinter.Button(argument_frame, text=f" {job['job_args']['frame_processors']} ", wraplength=325, justify='center')
            argument_button.pack(side='bottom', padx=5, fill='x', expand=False)
            argument_button.bind("<Button-1>", lambda event, j=job: edit_arguments_text(j))
    
    
    root.after(1000, update_job_listbox)
    root.mainloop()
    if __name__ == '__main__':
        edit_queue()


def setup_globals_from_job_args(job_args):
    """
    Set global values in facefusion.globals based on the argument parser values from the job.
    """
    ### maybe dont do not sure of bad effects - Set all current global values to None
    # for key in before_values:
        # setattr(facefusion.globals, key, None)

    # Update the globals with new values from job_args
    for key, value in job_args.items():
        setattr(facefusion.globals, key, value)

    return



##################################
#startup_init_checks_and_cleanup     
##################################
custom_print(f"{BLUE}Welcome Back To FaceFusion Queueing Addon\n\n")
custom_print(f"Checking Status{ENDC}\n\n")
if not os.path.exists(working_dir):
    os.makedirs(working_dir)
if not os.path.exists(media_cache_dir):
    os.makedirs(media_cache_dir)
default_values = get_values_from_globals("default_values")
create_and_verify_json(jobs_queue_file)
check_for_completed_failed_or_aborted_jobs()
custom_print(f"{GREEN}STATUS CHECK COMPLETED. {BLUE}You are now ready to QUEUE IT UP!{ENDC}")
print_existing_jobs()

# # Constants for Windows Power Management
# ES_CONTINUOUS = 0x80000000
# ES_SYSTEM_REQUIRED = 0x00000001

# def prevent_sleep():
    # """Prevent the system from going to sleep."""
    # os_type = platform.system()
    # if os_type == 'Windows':
        # ctypes.windll.kernel32.SetThreadExecutionState(
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        # )
    # elif os_type == 'Darwin':  # macOS
        # # Start a subprocess that uses caffeinate to prevent sleep
        # global caffeinate_process
        # caffeinate_process = subprocess.Popen("caffeinate")
        # custom_print("Prevented sleep on macOS using caffeinate.")
    # elif os_type == 'Linux':
        # # Start a subprocess that uses systemd-inhibit to prevent sleep
        # global inhibit_process
        # inhibit_process = subprocess.Popen(["systemd-inhibit", "--what=idle", "sleep infinity"],
                                           # stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # custom_print("Prevented sleep on Linux using systemd-inhibit.")

# def allow_sleep():
    # """Allow the system to go to sleep again."""
    # os_type = platform.system()
    # if os_type == 'Windows':
        # ctypes.windll.kernel32.SetThreadExecutionState(
            # ES_CONTINUOUS
        # )
    # elif os_type == 'Darwin':  # macOS
        # if 'caffeinate_process' in globals():
            # caffeinate_process.terminate()  # Terminate the caffeinate process
            # custom_print("Allowed sleep on macOS by terminating caffeinate.")
    # elif os_type == 'Linux':
        # if 'inhibit_process' in globals():
            # inhibit_process.terminate()  # Terminate the systemd-inhibit process
            # custom_print("Allowed sleep on Linux by terminating systemd-inhibit.")


def run(ui: gradio.Blocks) -> None:
    global server
    concurrency_count = min(8, multiprocessing.cpu_count())
    ui.queue(concurrency_count=concurrency_count).launch(show_api=False, inbrowser=True, quiet=False)


