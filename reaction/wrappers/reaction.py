import sys, itertools, timeit, os
import numpy as np
import pickle
from yarp.taffi_functions import table_generator,return_rings,adjmat_to_adjlist,canon_order
from yarp.properties import el_to_an,an_to_el,el_mass
from yarp.find_lewis import find_lewis,return_formals,return_n_e_accept,return_n_e_donate,return_formals,return_connections,return_bo_dict
from yarp.hashes import atom_hash,yarpecule_hash
from yarp.input_parsers import xyz_parse,xyz_q_parse,xyz_from_smiles, mol_parse
from yarp.misc import merge_arrays, prepare_list
from openbabel import pybel
from rdkit import Chem
from rdkit.Chem import EnumerateStereoisomers, AllChem, TorsionFingerprints, rdmolops, rdDistGeom
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions
from rdkit.ML.Cluster import Butina
from copy import deepcopy
from xtb import *
sys.path.append('/'.join(os.path.abspath(__file__).split('/')[:-2]))
from utils import *
from conf import *

class reaction:
    """
    Base class for storing information of a reaction and performing conformational sampling
    
    Attributes
    ----------

    reactant: yarpecule class for reactant

    product: yarpecule class for product

    opt: perform initial geometry optimization on product side. (default: False)
    
    """
    def __init__(self, reactant, product, args=dict(), opt=True):
        
        self.reactant=reactant
        self.product=product
        self.args=args
        self.conf_path=self.args["scratch_crest"]
        n_conf=self.args["n_conf"]
        self.n_conf=self.args["n_conf"]
        # safe check
        for count_i, i in enumerate(reactant.elements): reactant.elements[count_i]=i.capitalize()
        for count_i, i in enumerate(product.elements): product.elements[count_i]=i.capitalize()
        for count_i, i in enumerate(reactant.elements):
            if i != product.elements[count_i]:
                print("Fatal error: reactant and product are not same. Please check the input.....")
                exit()
        if opt: self.product=geometry_opt(self.product)
        self.reactant_dft_opt=dict()
        self.product_dft_opt=dict()
        self.reactant_conf=dict()
        self.product_conf=dict()
        self.reactant_energy=dict()
        self.product_energy=dict()
        self.reactant_inchi=return_inchikey(self.reactant)
        self.product_inchi=return_inchikey(self.product)
        self.reactant_smiles=return_smi_yp(self.reactant)
        self.reactant_smiles=return_smi_yp(self.product)
        self.rxn_conf=dict()
        self.id=0
        self.TS_guess=dict()
        self.TS_xtb=dict()
        self.TS_dft=dict()
        self.IRC_xtb=dict()
        self.IRC_dft=dict()
        self.constrained_TS=dict()
        if os.path.isdir(self.conf_path) is False: os.system('mkdir {}'.format(self.conf_path))

    def conf_rdkit(self):
        if self.args["strategy"]==0 or self.args["strategy"]==2:
            if os.path.isdir('{}/{}'.format(self.conf_path, self.reactant_inchi)) is False: os.system('mkdir {}/{}'.format(self.conf_path, self.reactant_inchi))
            if os.path.isfile('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.reactant_inchi)) is False:
                # sampling on reactant side
                mol_file='.reactant.tmp.mol'
                mol_write_yp(mol_file, self.reactant, append_opt=False)
                mol=Chem.rdmolfiles.MolFromMolFile(mol_file, removeHs=False)
                ids=AllChem.EmbedMultipleConfs(mol, useRandomCoords=True, numConfs=50, maxAttempts=1000000, pruneRmsThresh=0.1,\
                                               useExpTorsionAnglePrefs=False, useBasicKnowledge=True, enforceChirality=False)
                ids=list(ids)
                out=open('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.reactant_inchi), 'w+')
                os.system('rm .reactant.tmp.mol')
                for count_i, i in enumerate(ids):
                    geo=mol.GetConformer(i).GetPositions()
                    self.reactant_conf[count_i]=geo
                    out.write('{}\n\n'.format(len(self.reactant.elements)))
                    for count, e in enumerate(self.reactant.elements):
                        out.write('{} {} {} {}\n'.format(e.capitalize(), geo[count][0], geo[count][1], geo[count][2]))
            else:
                _, geo=xyz_parse('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.reactant_inchi), multiple=True)
                for count_i, i in enumerate(geo):
                    self.reactant_conf[count_i]=i
        if self.args["strategy"]==1 or self.args["strategy"]==2:
            if os.path.isdir('{}/{}'.format(self.conf_path, self.product_inchi)) is False: os.system('mkdir {}/{}'.format(self.conf_path, self.product_inchi))
            if os.path.isfile('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.product_inchi)) is False:
                # sampling on reactant side
                mol_file='.product.tmp.mol'
                mol_write_yp(mol_file, self.product, append_opt=False)
                mol=Chem.rdmolfiles.MolFromMolFile(mol_file, removeHs=False)
                ids=AllChem.EmbedMultipleConfs(mol, useRandomCoords=True, numConfs=50, maxAttempts=1000000, pruneRmsThresh=0.1,\
                                               useExpTorsionAnglePrefs=False, useBasicKnowledge=True, enforceChirality=False)
                ids=list(ids)
                out=open('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.product_inchi), 'w+')
                os.system('rm .product.tmp.mol')
                for count_i, i in enumerate(ids):
                    geo=mol.GetConformer(i).GetPositions()
                    self.product_conf[count_i]=geo
                    out.write('{}\n\n'.format(len(self.product.elements)))
                    for count, e in enumerate(self.product.elements):
                        out.write('{} {} {} {}\n'.format(e.capitalize(), geo[count][0], geo[count][1], geo[count][2]))
            else:
                _, geo=xyz_parse('{}/{}/rdkit_conf.xyz'.format(self.conf_path, self.product_inchi), multiple=True)
                for count_i, i in enumerate(geo):
                    self.product_conf[count_i]=i

    def rxn_conf_generation(self, logging_queue):

        job_id=f"{self.reactant_inchi}_{self.id}"
        
        RG=self.reactant.geo
        RE=self.reactant.elements
        R_adj=self.reactant.adj_mat
        R_bond_mats=self.reactant.bond_mats

        PG=self.product.geo
        PE=self.product.elements
        P_adj=self.product.adj_mat
        P_bond_mats=self.product.bond_mats

        tmp_rxn_dict=dict()
        count=0
        # Create a dictionary to store the conformers and product/reactant bond mat.
        if self.args["strategy"]!=0:
            for i in self.product_conf.keys():
                tmp_rxn_dict[count]={"E": RE, "bond_mat_r": R_bond_mats[0], "G": deepcopy(self.product_conf[i]), 'direct':'B'}
                count=count+1
        if self.args["strategy"]!=1:
            for i in self.reactant_conf.keys():
                tmp_rxn_dict[count]={"E": RE, "bond_mat_r": P_bond_mats[0], "G": deepcopy(self.reactant_conf[i]), 'direct': "F"}
                count=count+1
        # load ML model to find conformers 
        if len(tmp_rxn_dict)>3*self.n_conf: model=pickle.load(open(os.path.join(self.args['model_path'],'rich_model.sav'), 'rb'))
        else: model=pickle.load(open(os.path.join(self.args['model_path'],'poor_model.sav'), 'rb'))

        ind_list, pass_obj_values=[], []
        for conf_ind, conf_entry in tmp_rxn_dict.items():
            # apply force-field optimization
            # apply xTB-restrained optimization soon!
            Gr = opt_geo(conf_entry['E'],conf_entry['G'],conf_entry['bond_mat_r'],ff=self.args['ff'],step=100,filename=f'tmp_{job_id}')
            if len(Gr)==0: continue
            tmp_xyz_p = f"{self.args['scratch_xtb']}/{job_id}_p.xyz"
            xyz_write(tmp_xyz_p,conf_entry['E'],Gr)
            tmp_xyz_r = f"{self.args['scratch_xtb']}/{job_id}_r.xyz"
            xyz_write(tmp_xyz_r,conf_entry['E'],conf_entry['G'])

            # calculate indicator
            indicators = return_indicator(conf_entry['E'],conf_entry['G'],Gr,namespace=f'tmp_{job_id}')
            reactant=io.read(tmp_xyz_r)
            product=io.read(tmp_xyz_p)
            minimize_rotation_and_translation(reactant,product)
            io.write(tmp_xyz_p,product)
            _,Gr_opt = xyz_parse(tmp_xyz_p)
            indicators_opt = return_indicator(conf_entry['E'],conf_entry['G'],Gr_opt,namespace=f'tmp_{job_id}')

            # if applying ase minimize_rotation_and_translation will increase the intended probability, use the rotated geometry
            if model.predict_proba(indicators)[0][1] < model.predict_proba(indicators_opt)[0][1]: indicators, Gr = indicators_opt, Gr_opt
            # check whether the channel is classified as intended and check uniqueness
            if model.predict_proba(indicators)[0][1] > 0.4 and check_duplicate(indicators,ind_list,thresh=0.025):
                ind_list.append(indicators)
                pass_obj_values.append((model.predict_proba(indicators)[0][0],deepcopy(conf_entry['G']),Gr,deepcopy(conf_entry['direct'])))

            # remove tmp file
            if os.path.isfile(tmp_xyz_r): os.remove(tmp_xyz_r)
            if os.path.isfile(tmp_xyz_p): os.remove(tmp_xyz_p)

        pass_obj_values=sorted(pass_obj_values, key=lambda x: x[0])
        N_conf=0
        for item in pass_obj_values:
            input_type=item[3]
            tmp_xyz_r = f"{self.args['scratch_xtb']}/{job_id}_r.xyz"
            tmp_xyz_p = f"{self.args['scratch_xtb']}/{job_id}_p.xyz"
            xyz_write(tmp_xyz_r, RE, item[1])
            xyz_write(tmp_xyz_p, RE, item[2])
            if self.args['opt']:
                if self.args['low_solvation']:
                    solvation_model, solvent = self.args['low_solvation'].split('/')
                    optjob = XTB(input_geo=tmp_xyz_p,work_folder=self.args['scratch_xtb'],jobtype=['opt'],jobname=f'opt_{job_id}_p',solvent=solvent,\
                                 solvation_model=solvation_model,charge=self.args['charge'],multiplicity=self.args['multiplicity'])
                else:
                    optjob = XTB(input_geo=tmp_xyz_p,work_folder=self.args['scratch_xtb'],jobtype=['opt'],jobname=f'opt_{job_id}_p',charge=self.args['charge'],multiplicity=self.args['multiplicity'])

                optjob.execute()

                if optjob.optimization_success():
                    _, Gr = optjob.get_final_structure()
                else:
                    #logger.info(f"xtb geometry optimization fails for the other end of {job_id} (conf: {conf_ind}), will use force-field optimized geometry for instead")
                    #Gr = item[2]
                    continue

                xyz_write(tmp_xyz_p,conf_entry['E'],Gr)

            if input_type=='F':
                _, rg=xyz_parse(tmp_xyz_r)
                _, pg=xyz_parse(tmp_xyz_p)
                self.rxn_conf[N_conf]={"R": rg, "P": pg}
                os.system(f"rm {tmp_xyz_r}")
                os.system(f"rm {tmp_xyz_p}")
                #os.system(f"cp {tmp_xyz_r} {self.args['conf_output']}/{job_id}_{N_conf}.xyz; cat {tmp_xyz_p} >> {self.args['conf_output']}/{job_id}_{N_conf}.xyz;rm {tmp_xyz_r} {tmp_xyz_p}")
            else:
                _, rg=xyz_parse(tmp_xyz_p)
                _, pg=xyz_parse(tmp_xyz_r)
                self.rxn_conf[N_conf]={"R": rg, "P": pg}
                os.system(f"rm {tmp_xyz_r}")
                os.system(f"rm {tmp_xyz_p}")
                #os.system(f"cp {tmp_xyz_p} {self.args['conf_output']}/{job_id}_{N_conf}.xyz; cat {tmp_xyz_r} >> {self.args['conf_output']}/{job_id}_{N_conf}.xyz;rm {tmp_xyz_r} {tmp_xyz_p}")
            N_conf=N_conf+1
            if N_conf>=self.args["n_conf"]: break

        if len(pass_obj_values) == 0:
            print(f"WARNING: None of the reaction conformation can be generated for the input reaction {job_id}. please check this reaction to make sure it is a vaild one")

        # add a joint-opt alignment if too few alignments pass the criteria
        # will add soon
        return
