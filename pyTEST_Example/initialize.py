import os

import pickle
from utils import *

def load_pickle(rxns_pickle):
    rxns=pickle.load(open(rxns_pickle, 'rb'))
    return rxns

def write_pickle(name, data):
    with open(name, "wb") as f:
        pickle.dump(data, f)

def DFT_Initialize(args):
    keys = [i for i in args.keys()]

    if "verbose" not in keys:
        args['verbose'] = False
    else:
        args['verbose'] = bool(args['verbose'])

    if not "solvation" in keys: args['solvation'] = False

    if args["solvation"]: args["solvation_model"], args["solvent"]=args["solvation"].split('/')
    else: args["solvation_model"], args["solvent"]="CPCM", False
    args["scratch_dft"]=f'{args["scratch"]}/DFT'
    args["scratch_crest"]=f'{args["scratch"]}/conformer'
    if os.path.isdir(args["scratch"]) is False: os.mkdir(args["scratch"])
    if os.path.isdir(args["scratch_dft"]) is False: os.mkdir(args["scratch_dft"])
    if args["reaction_data"] is None: args["reaction_data"]=args["scratch"]+"/reaction.p"

    #Zhao's note: for CREST (Reactant/Product)
    if "low_solvation" not in keys:
        args["low_solvation"]=False
        args["low_solvation_model"]="alpb"
        args["solvent"]=False
        args["solvation_model"]="CPCM"
    else:
        args["low_solvation_model"], args["solvent"]=args['low_solvation'].split('/')

    #Zhao's note: an option to send emails to the user if they specify an email address
    if "email_address" not in keys:
        args["email_address"] = ""

    #Zhao's note: for using non-default crest executable
    #Just provide the folder, not the executable
    #Need the final "/"
    if not 'crest_path' in keys:
        args['crest_path'] = os.popen('which crest').read().rstrip()
    else:
        args['crest_path'] = args['crest_path'] + "crest"

    # Zhao's note: convert arg['mem'] into float, then convert to int later #
    args['mem'] = float(args['mem'])
    args['dft_nprocs'] = int(args['dft_nprocs'])
    args['dft_ppn'] = int(args['dft_ppn'])
    # Zhao's note: process mix_basis input keywords in the yaml file
    if "dft_mix_basis" in keys:
        process_mix_basis_input(args)
    else:
        args['dft_fulltz_level_correction'] = False
        args['dft_mix_firstlayer'] = False

    #Zhao's note: option to use "TS_Active_Atoms" in ORCA
    #sometimes useful, sometimes not...
    if not 'dft_TS_Active_Atoms' in keys:
        args['dft_TS_Active_Atoms'] = False
    else:
        args['dft_TS_Active_Atoms'] = bool(args['dft_TS_Active_Atoms'])

    if os.path.exists(args["reaction_data"]) is False:
        print("No reactions are provided for refinement....")
        return
        #exit()
    rxns=load_pickle(args["reaction_data"])
    for count, i in enumerate(rxns):
        rxns[count].args=args
        RP_diff_Atoms = []
        if(args['dft_TS_Active_Atoms'] or args['dft_mix_firstlayer']):
            adj_diff_RP=np.abs(rxns[count].product.adj_mat - rxns[count].reactant.adj_mat)
            # Get the elements that are non-zero #
            RP_diff_Atoms = np.where(adj_diff_RP.any(axis=1))[0]
            if(args['verbose']): print(f"Atoms {RP_diff_Atoms} have changed between reactant/product\n")
            rxns[count].args['Reactive_Atoms'] = RP_diff_Atoms
        treat_mix_lot_metal_firstLayer(args, i.reactant.elements, i.reactant.geo)
        treat_mix_lot_metal_firstLayer(args, i.product.elements,  i.product.geo)

    # Run DFT optimization first to get DFT energy
    # print("Running DFT optimization")
    #print(rxns)
    # Skip Reactant/Product to just run TS Optimization
    if not 'rp_opt' in keys:
        args['rp_opt'] = True
    else:
        args['rp_opt'] = bool(args['rp_opt'])
