import pytest, os, re, yaml
import shutil
import subprocess
#import yarp as yp
#from calculator import add
'''
import yarp as yp
import numpy as np
import threading
import pickle
import multiprocessing as mp
from multiprocessing import Queue
from logging.handlers import QueueHandler
from joblib import Parallel, delayed
from yarp.find_lewis import all_zeros
from yarp.find_lewis import bmat_unique
import os, sys, yaml, fnmatch
import logging
from openbabel import pybel
from utils import *
from wrappers.reaction import *
from job_mapping import *
from wrappers.crest import CREST
from qc_jobs import *
from conf import *
from analyze_functions import *
from wrappers.pysis import PYSIS
from wrappers.gsm import GSM
'''
def truthy(value):
    return bool(value)
def falsy(value):
    return not bool(value)

def check_metal(xyz):

    finish = False
    FeCO5 = yp.yarpecule(xyz)
    # first check adj_mat
    nBonds = 20
    nE = 58
    nDative= 5
    if(FeCO5.adj_mat.sum() == nBonds and FeCO5.bond_mats[0].sum() == nE):
        # then check bmat
        if(FeCO5.adj_mat.sum(axis=1)[0]==nDative):
            finish = True
    return finish

def form_bond(a, hashes, nform):
    mols = [a]
    for i in range(0, nform):
        mols = list(set([ y for y in yp.form_bonds(mols,hashes=hashes)]))
        hashes.update([ _.hash for _ in mols ])
        print(f"form {i} bond resulted in {len(mols)} new products")

def break_bond(a, hashes, nbreak):
    mols = [a]
    mols = list(set([ y for y in yp.break_bonds(mols,n=nbreak)]))
    hashes.update([ _.hash for _ in mols ])
    print(f"break {nbreak} bond resulted in {len(mols)} new products")

def rxn_setYAML(current_path, model_path, gsm_path, conda_path):
    if not os.path.isfile("template.yaml"): return
    shutil.copyfile("template.yaml", "parameters.yaml")
    if not os.path.isfile("parameters.yaml"): return

    with open('parameters.yaml', 'r') as file: filedata = file.read()
    # Replace the target string
    filedata = filedata.replace('{current_path}',  current_path)
    filedata = filedata.replace('{model_path}',    model_path)
    filedata = filedata.replace('{gsm_file_path}', gsm_path)
    filedata = filedata.replace('{conda_path}',    conda_path)
    with open('parameters.yaml', 'w') as file: file.write(filedata)

def rxn_xtb():
    #subprocess.call("crest ", shell=True)
    #subprocess.call("pysis ", shell=True)
    #subprocess.call("xtb "  , shell=True)

    subprocess.call("python main_xtb.py parameters.yaml", shell=True)
    #exec(open("main_xtb.py").read()) 


def test_file():
    current_directory = os.getcwd() + '/'
    CONDA="CONDA_PATH"
    rxn_setYAML(current_path = current_directory, 
            model_path = f"{current_directory}/bin",
            gsm_path   = f"{current_directory}/bin/inpfileq",
            conda_path = f"{CONDA}/bin")

    rxn_xtb()
    with open('parameters.yaml', 'rb') as f: conf = yaml.safe_load(f.read())
    #RUN(conf)
    '''
    assert  os.path.exists('FeCO5.xyz')
    assert  check_metal("FeCO5.xyz")
    print("Organometallics CHECK FINISHED\n")
    reactant="C=CC=C.C=C"
    a = yp.yarpecule(reactant)
    hashes = set([a.hash])
    print(f"reactant: {reactant}")
    form_bond(a, hashes, 2)
    break_bond(a, hashes, 2)
    assert len(hashes) == 29
    '''
