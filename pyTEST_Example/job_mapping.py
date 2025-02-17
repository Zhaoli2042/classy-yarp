import os,sys
import numpy as np
import logging
import pickle
import time
from copy import deepcopy
from collections import Counter
import multiprocessing as mp
from multiprocessing import Queue
from logging.handlers import QueueHandler
from concurrent.futures import ProcessPoolExecutor, TimeoutError

from ase import io
from ase.build import minimize_rotation_and_translation
from scipy.spatial.distance import cdist
from xgboost import XGBClassifier
from wrappers.xtb import XTB

from yarp.taffi_functions import table_generator, xyz_write
from yarp.find_lewis import find_lewis
from utils import return_metal_constraint

def logger_process(queue, logging_path):                                                                                                       
    """A child process for logging all information from other processes"""
    logger = logging.getLogger("YARPrun")
    logger.addHandler(logging.FileHandler(logging_path))
    logger.setLevel(logging.INFO)
    while True:
        message = queue.get()
        if message is None:
            break
        logger.handle(message)

def match_first_two_elements(input_list, list_of_lists):
    # Extract the first two elements of the input list
    first_two_input = sorted(input_list[:2])
    
    # Iterate through each sublist in the list of lists
    for sublist in list_of_lists:
        # Sort the first two elements of the current sublist for an order-independent comparison
        first_two_sublist = sorted(sublist[:2])
        # Check if the first two elements match
        if first_two_input == first_two_sublist:
            return True  # Match found
    return False  # No match found

def process_input_rxn(rxns, args={}):
    job_mapping=dict()
    process_id=mp.current_process().pid
    for i in rxns:
        count_i, rxn, args=i
        RE=rxn.reactant.elements
        PE=rxn.product.elements
        RG=rxn.reactant.geo
        PG=rxn.product.geo
        R_inchi=rxn.reactant_inchi
        P_inchi=rxn.product_inchi
        R_constraint=return_metal_constraint(rxn.reactant)
        P_constraint=return_metal_constraint(rxn.product)

        #Zhao's note: added dist constraint for both reactant and product
        if(args['constraint'] and not args['product_dist_constraint'] is None):
            total_constraints = []
            inp_list = args['product_dist_constraint'].split(',')
            for a in range(0, int(len(inp_list) / 3)):
                arg_list = [int(inp_list[a * 3]), int(inp_list[a * 3 + 1]), float(inp_list[a * 3 + 2])]
                total_constraints.append(arg_list)
            for constraints in total_constraints:
                #Check for overlaps in the atom numbers
                if not match_first_two_elements(constraints, P_constraint):
                    P_constraint.append(constraints)

        if(args['constraint'] and not args['reactant_dist_constraint'] is None):
            total_constraints = []
            inp_list = args['reactant_dist_constraint'].split(',')
            for a in range(0, int(len(inp_list) / 3)):
                arg_list = [int(inp_list[a * 3]), int(inp_list[a * 3 + 1]), float(inp_list[a * 3 + 2])]
                total_constraints.append(arg_list)
            for constraints in total_constraints:
                #Check for overlaps in the atom numbers
                if not match_first_two_elements(constraints, R_constraint):
                    R_constraint.append(constraints)

        R_ADJMAT = table_generator(RE, RG)
        P_ADJMAT = table_generator(PE, PG)
        np.set_printoptions(threshold=sys.maxsize)

        #exit()

        if args["strategy"]!=0:
            if P_inchi not in job_mapping:

                job_mapping[P_inchi]={'jobs': [f'{count_i}-P'], 'id': len(job_mapping)}
                xyz_write(f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", PE, PG)
                if args["low_solvation"]:
                    solvation_model, solvent = args["low_solvation"].split("/")
                    optjob=XTB(input_geo=f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", work_folder=args["scratch_xtb"],lot=args["lot"], jobtype=["opt"],\
                               solvent=solvent, solvation_model=solvation_model, jobname=f"{process_id}_{len(job_mapping)}_opt", charge=args["charge"], multiplicity=args["multiplicity"])
                    if P_constraint!=[]: optjob.add_command(distance_constraints=P_constraint)
                    optjob.execute()
                else:
                    optjob=XTB(input_geo=f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", work_folder=args["scratch_xtb"], lot=args["lot"], jobtype=["opt"],\
                               jobname=f"{process_id}_{len(job_mapping)}_opt", charge=args["charge"], multiplicity=args["multiplicity"])
                    if P_constraint!=[]: optjob.add_command(distance_constraints=P_constraint)
                    optjob.execute()
                if optjob.optimization_success():
                    E, G=optjob.get_final_structure()
                    job_mapping[P_inchi]["E"], job_mapping[P_inchi]["G"]=E, G
                else:
                    sys.exit(f"xtb geometry optimization fails for {P_inchi}, please check or remove this reactions")
            else: job_mapping[P_inchi]["jobs"].append(f"{count_i}-P")
        if args["strategy"]!=1:
            if R_inchi not in job_mapping:

                job_mapping[R_inchi]={"jobs": [f"{count_i}-R"], "id": len(job_mapping)}
                xyz_write(f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", RE, RG)
                if args["low_solvation"]:
                    solvation_model, solvent = args["low_solvation"].split("/")
                    optjob=XTB(input_geo=f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", work_folder=args["scratch_xtb"],lot=args["lot"], jobtype=["opt"],\
                               solvent=solvent, solvation_model=solvation_model, jobname=f"{process_id}_{len(job_mapping)}_opt", charge=args["charge"], multiplicity=args["multiplicity"])
                    if R_constraint!=[]: optjob.add_command(distance_constraints=R_constraint)
                    optjob.execute()
                else:
                    optjob=XTB(input_geo=f"{args['scratch_xtb']}/{process_id}_{len(job_mapping)}_init.xyz", lot=args["lot"], work_folder=args["scratch_xtb"], jobtype=["opt"],\
                               jobname=f"{process_id}_{len(job_mapping)}_opt", charge=args["charge"], multiplicity=args["multiplicity"])
                    if R_constraint!=[]: optjob.add_command(distance_constraints=R_constraint)
                    optjob.execute()
                if optjob.optimization_success():
                    E, G=optjob.get_final_structure()
                    job_mapping[R_inchi]["E"], job_mapping[R_inchi]["G"]=E, G
                else:
                    sys.exit(f"xtb geometry optimization fails for {R_inchi}, please check or remove this reactions")
            else: job_mapping[R_inchi]["jobs"].append(f"{count_i}-R")
    return job_mapping

def merge_job_mappings(all_job_mappings):
    merged_mapping = dict()
    for job_mapping in all_job_mappings:
        for inchi, jobi in job_mapping.items():
            if inchi in merged_mapping.keys():
                for idx in jobi["jobs"]: merged_mapping[inchi]["jobs"].append(idx)
            else: merged_mapping[inchi]=jobi.copy()
    id_mapping={inchi: sorted(info['jobs'])[0] for inchi, info in merged_mapping.items()}
    job_list=sorted(list(id_mapping.values()))
    for inchi, info in merged_mapping.items():
        info['id']=job_list.index(id_mapping[inchi])+1
    return merged_mapping

def monitor_jobs(slurm_jobs):
    '''
    Function that sleeps the script until jobids are no longer in a running or pending state in the queue
    '''
    while True:
        for slurm_job in slurm_jobs:
            if slurm_job.status() == 'FINISHED':
                slurm_jobs.remove(slurm_job)
        if not slurm_jobs:
            break
        time.sleep(60)
    return    
#Zhao's note: write the jobs to txt file for monitoring#
def write_to_last_job(slurm_jobs):
    with open('last_jobs.txt', 'w') as file:
        for slmjob in slurm_jobs:
            file.write(slmjob.job_id + '\n')
