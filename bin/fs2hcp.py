#!/usr/bin/env python
"""
Converts a freesurfer recon-all output to a HCP data directory

Usage:
  func2hcp.py [options] <Subject>

Arguments:
    <Subject>               The Subject ID in the HCP data folder

Options:
  --hcp-data-dir PATH         Path to the HCP_DATA directory (overides the HCP_DATA environment variable)
  --fs-subjects-dir PATH      Path to the freesurfer SUBJECTS_DIR directory (overides the SUBJECTS_DIR environment variable)
  -v,--verbose                Verbose logging
  --debug                     Debug logging in Erin's very verbose style
  -n,--dry-run                Dry run
  -h,--help                   Print help

DETAILS
Adapted from the PostFreeSurferPipeline module of the HCP Pipeline

Written by Erin W Dickie, Jan 19, 2017
"""
from docopt import docopt
import os
import math
import tempfile
import shutil
import subprocess
import platform
import logging


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def run(cmd, dryrun=False, echo=True, supress_stdout = False):
    """
    Runscommand in default shell, returning the return code. And logging the output.
    It can take a the cmd argument as a string or a list.
    If a list is given, it is joined into a string.
    There are some arguments for changing the way the cmd is run:
       dryrun:     do not actually run the command (for testing) (default: False)
       echo:       Print the command to the log (info (level))
       supress_stdout:  Any standard output from the function is printed to the log at "debug" level but not "info"
    """

    global DRYRUN
    dryrun = DRYRUN

    if type(cmd) is list:
        thiscmd = ' '.join(cmd)
    else: thiscmd = cmd
    if echo:
        logger.info("Running: {}".format(thiscmd))
    if dryrun:
        logger.info('Doing a dryrun')
        return 0
    else:
        p = subprocess.Popen(thiscmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if p.returncode:
            logger.error('cmd: {} \n Failed with returncode {}'.format(thiscmd, p.returncode))
        if supress_stdout:
            logger.debug(out)
        else:
            logger.info(out)
        if len(err) > 0 : logger.warning(err)
        return p.returncode

def getstdout(cmdlist):
   ''' run the command given from the cmd list and report the stdout result'''
   p = subprocess.Popen(cmdlist, stdout=PIPE, stderr=PIPE)
   stdout, stderr = p.communicate()
   if p.returncode:
       logger.error('cmd: {} \n Failed with error: {}'.format(cmdlist, stderr))
   return stdout


SpacesDict = {
    'native':{'Folder' : "$AtlasSpaceFolder"/"$NativeFolder", 'ROI': 'roi'},
    '{}k'.format(HighResMesh):{'Folder' : AtlasSpaceFolder, 'ROI': 'atlasroi'},
}
for LowResMesh in LowResMeshes:
    SpacesDict['{}k'.LowResMesh] = {'Folder': os.path.join(AtlasSpaceFolder,'fsaverage_LR{}'.format(LowResMesh)),
                                    'ROI' = 'atlasroi'}

dscalarSettings = {
    'sulc': {
        'fsname': 'sulc',
        'map_posfix': '_Sulc',
        'palette_mode': 'MODE_AUTO_SCALE_PERCENTAGE',
        'palette_options': '-pos-percent 2 98 -palette-name Gray_Interp -disp-pos true -disp-neg true -disp-zero true',
        'mask_medial' : False
             },
    'curvature': {
        'fsname': 'curv',
        'map_posfix': '_Curvature',
        'palette_mode': 'MODE_AUTO_SCALE_PERCENTAGE',
        'palette_options': '-pos-percent 2 98 -palette-name Gray_Interp -disp-pos true -disp-neg true -disp-zero true',
        'mask_medial' : True
    },
    'thickness': {
        'fsname': 'thickness'
        'map_posfix':'_Thickness',
        'palette_mode': 'MODE_AUTO_SCALE_PERCENTAGE',
        'palette_options': '-pos-percent 4 96 -interpolate true -palette-name videen_style -disp-pos true -disp-neg false -disp-zero false',
        'mask_medial' : True
    },
    'ArealDistortion_FS': {
        'map_posfix':'_ArealDistortion_FS',
        'palette_mode': 'MODE_USER_SCALE',
        'palette_options': '-pos-user 0 1 -neg-user 0 -1 -interpolate true -palette-name ROY-BIG-BL -disp-pos true -disp-neg true -disp-zero false',
        'mask_medial' : False
    }
}

if  RegName == "MSMSulc":
    dscalarSettings['ArealDistortion_MSMSulc'] = {
        'map_posfix':'_ArealDistortion_MSMSulc',
        'palette_mode': 'MODE_USER_SCALE',
        'palette_options': '-pos-user 0 1 -neg-user 0 -1 -interpolate true -palette-name ROY-BIG-BL -disp-pos true -disp-neg true -disp-zero false',
        'mask_medial' : False
    }



def create_dlabel_add_to_spec(meshname, mapname, Subject, meshSettings = meshSettings):
    '''
    create the dense labels that combine the two surfaces
    set the meta-data and add them to the spec_file
    They read the important options from two dictionaries
    '''
    meshDict = meshSettings[meshname]
    fvars = {'Subject' : Subject, 'map': mapname, 'mesh' : meshname,
        'roi' : meshDict['ROI']}
    dlabel_file = os.path.join(meshDict['Folder'],
        '{Subject}.{map}.{mesh}.dlabel.nii'.format(**fvars))
    run(['wb_command', '-cifti-create-label', dlabel_file,
        '-left-label', os.path.join(tmpdir, meshname,
            '{Subject}.L.${map}.{mesh}.label.gii'.format(**fvars)),
        '-roi-left', os.path.join(meshDict['Folder'],
            '{Subject}.L.{roi}.{mesh}.shape.gii'.format(**fvars)),
        '-right-label', os.path.join(tmpdir, meshname,
            '{Subject}.R.{map}.{mesh}.label.gii'.format(**fvars)),
        '-roi-right', os.path.join(meshDict['Folder'],
            '{Subject}.R.{roi}.{mesh}.shape.gii'.format(**fvars))])
    run(['wb_command', '-set-map-names', dlabel_file,
        '-map', '1', '{Subject}_{mapname}'.format(**fvars)])
    run(['wb_command', '-add-to-spec-file',
        os.path.join(meshDict['Folder'],'{Subject}.{mesh}.wb.spec'.format(**fvars)),
        'INVALID', dlabel_file])

def write_cras_file(FreeSurferFolder):
   #  #Find c_ras offset between FreeSurfer surface and volume and generate matrix to transform surfaces
   # if [ ! -e "$FreeSurferFolder"/mri/c_ras.mat ] ; then
   #   MatrixX=`mri_info "$FreeSurferFolder"/mri/brain.finalsurfs.mgz | grep "c_r" | cut -d "=" -f 5 | sed s/" "/""/g`
   #   MatrixY=`mri_info "$FreeSurferFolder"/mri/brain.finalsurfs.mgz | grep "c_a" | cut -d "=" -f 5 | sed s/" "/""/g`
   #   MatrixZ=`mri_info "$FreeSurferFolder"/mri/brain.finalsurfs.mgz | grep "c_s" | cut -d "=" -f 5 | sed s/" "/""/g`
   #   echo "1 0 0 ""$MatrixX" > "$FreeSurferFolder"/mri/c_ras.mat
   #   echo "0 1 0 ""$MatrixY" >> "$FreeSurferFolder"/mri/c_ras.mat
   #   echo "0 0 1 ""$MatrixZ" >> "$FreeSurferFolder"/mri/c_ras.mat
   #   echo "0 0 0 1" >> "$FreeSurferFolder"/mri/c_ras.mat
   # fi
   crat_mat = None
   return(cras_mat)


def calc_ArealDistortion_gii(sphere_pre, sphere_reg, AD_gii_out, map_prefix, map_posfix):
    ''' calculate Areal Distortion Map (gifti) after registraion
        Arguments:
            sphere_pre    Path to the pre registration sphere (gifti)
            sphere_reg    Path to the post registration sphere (gifti)
            AD_gii_out    Path to the Area Distortion gifti output
            map_prefix    Prefix added to the map-name meta-data
            map_postfix   Posfix added to the map-name meta-data
    '''
    ## set temp file paths
    va_tmpdir = tempfile.mkdtemp()
    sphere_pre_va = os.path.join(va_tmpdir, 'sphere_pre_va.shape.gii')
    sphere_reg_va = os.path.join(va_tmpdir, 'sphere_reg_va.shape.gii')
    ## calculate surface vertex areas from pre and post files
    run(['wb_command', '-surface-vertex-areas', sphere_pre, sphere_pre_va])
    run(['wb_command', '-surface-vertex-areas', sphere_reg, sphere_reg_va])
    ## caluculate Areal Distortion using the vertex areas
    run(['wb_command', '-metric-math',
        '(ln(spherereg / sphere) / ln(2))',
        AD_gii_out,
        '-var', 'sphere', sphere_pre_va,
        '-var', 'spherereg', sphere_reg_va])
    ## set meta-data for the ArealDistotion files
    run(['wb_command', '-set-map-names', AD_gii_out,
        '-map', '1', '{}_Areal_Distortion_{}'.format(map_prefix. map_postfix)])
    run(['wb_command', '-metric-palette', AD_gii_out, 'MODE_AUTO_SCALE',
        '-palette-name', 'ROY-BIG-BL',
        '-thresholding', 'THRESHOLD_TYPE_NORMAL', 'THRESHOLD_TEST_SHOW_OUTSIDE', '-1', '1'])
    shutil.rmtree(va_tmpdir)

def resample_surf_and_add_to_spec(surf_in, surf_out, current_sphere, new_sphere,
        spec_file, spec_structure):
    '''
    resample surface files and add them to the resampled spaces spec file
    uses wb_command -surface-resample with BARYCENTRIC method
    Arguments:
        surf_in         Path to surface to resample
        surf_out        Output path of resampled surface
        current_sphere  Path to sphere with resolution of surf_in
        new_sphere      Path to sphere with desired resolution of surf_out
        spec_file       Spec file of output resolution space
        spec_structure  Structure for the spec_file call
    '''
    run(['wb_command', '-surface-resample', surf_in,
        current_sphere, new_sphere, 'BARYCENTRIC', surf_out])
    run(['wb_command', '-add-to-spec-file', spec_file, spec_structure, surf_out])

def make_inflated_surfaces(mid_surf, spec_file, Structure, iterations_scale = 2.5):
    '''
    make inflated and very_inflated surfaces from the mid surface file
    adds the surfaces to the spec_file
    filenames for inflated and very inflated surfaces are made from mid_surf filename
    '''
    bname = os.path.basename(mid_surf)
    dname = os.path.dirname(mid_surf)
    infl_surf = os.path.join(dname, bname.replace('midthickness','inflated'))
    vinfl_surf = os.path.join(dname , bname.replace('midthickness','very_inflated'))
    run(['wb_command', '-surface-generate-inflated', mid_surf,
      infl_surf, vinfl_surf, '-iterations-scale', str(iterations_scale)])
    run(['wb_command', '-add-to-spec-file', spec_file, Structure, infl_surf])
    run(['wb_command', '-add-to-spec-file', spec_file, Structure, vinfl_surf])


def resample_and_mask_metric(RegSphere, current_mesh, dest_mesh,
        Subject, Hemisphere, MapName,
        meshSettings = meshSettings, mapSettings = dscalarSettings):
    '''
    rasample the metric files to a different mesh than mask out the medial wall
    uses wb_command -metric-resample with 'ADAP_BARY_AREA' method
    To remove masking steps the roi can be set to None
    '''
    for MapName in mapSettings.keys():
        metric_in = os.path.join(tmpdir, current_mesh,
            '{}.{}.{}.{}.shape.gii'.format(Subject, Hemisphere, MapName, current_mesh))
        metric_out = os.path.join(tmpdir, dest_mesh,
            '{}.{}.{}.{}.shape.gii'.format(Subject, Hemisphere, MapName, dest_mesh))
        current_midthickness = os.path.join(current_mesh['Folder'],
            '{}.{}.midthickness.{}.surf.gii'.format(Subject, Hemisphere, current_mesh))
        new_midthickness = os.path.join(dest_mesh['Folder'],
            '{}.{}.midthickness.{}.surf.gii'.format(Subject, Hemisphere, dest_mesh))
        if mapSettings[mapname]['mask_medial']:
            current_roi = os.path.join(current_mesh['Folder'],
                '{}.{}.{}.{}.shape.gii'.format(Subject, Hemisphere,
                                                meshDict[current_mesh]['ROI'], current_mesh))
            new_roi = os.path.join(current_mesh['Folder'],
                '{}.{}.{}.{}.shape.gii'.format(Subject, Hemisphere,
                                                meshDict[dest_mesh]['ROI'], dest_mesh))
            run(['wb_command', '-metric-resample',
                metric_in, RegSphere, new_sphere, 'ADAP_BARY_AREA', metric_out,
                '-area-surfs', current_midthickness, new_midthickness,
                '-current-roi', current_roi])
            run(['wb_command', '-metric-mask', metric_out, new_roi, metric_out])
        else:
            run(['wb_command', '-metric-resample',
                metric_in, RegSphere, new_sphere, 'ADAP_BARY_AREA', metric_out,
                '-area-surfs', current_midthickness, new_midthickness])

def create_dscalar_add_to_spec(meshname, mapname, Subject,
        mapSettings = dscalarSettings, meshSettings = meshSettings):
    '''
    create the dense scalars that combine the two surfaces
    set the meta-data and add them to the spec_file
    They read the important options from two dictionaries
    '''
    fvars = {'Subject' : Subject, 'map': mapname, 'mesh' : meshname,
        'postfix' : mapSettings[mapname]['postfix'], 'roi' : meshDict['ROI']}
    meshDict = meshSettings[meshname]
    dscalar_file = os.path.join(meshDict['Folder'],
        '{Subject}.{map}.{mesh}.dscalar.nii'.format(**fvars))
    ## combine L and R metrics into dscalar.nii file
    if mapSettings[mapname]['mask_medial']:
        run(['wb_command', '-cifti-create-dense-scalar', dscalar_file,
        '-left-metric', os.path.join(tmpdir, meshname,
            '{Subject}.L.{map}.{mesh}.shape.gii'.format(**fvars)),
        '-roi-left', os.path.join(meshDict['Folder'],
            '{Subject}.L.{roi}.{mesh}.shape.gii'.format(**fvars)),
        '-right-metric', os.path.join(tmpdir, meshname,
            '{Subject}.R.{map}.{mesh}.shape.gii'.format(**fvars)),
        '-roi-right', os.path.join(meshDict['Folder'],
            '{Subject}.R.{roi}.{mesh}.shape.gii'.format(**fvars))])
    else:
        run(['wb_command', '-cifti-create-dense-scalar', dscalar_file,
        '-left-metric', os.path.join(tmpdir, meshname,
            '{Subject}.L.{map}.{mesh}.shape.gii'.format(**fvars)),
        '-right-metric', os.path.join(tmpdir, meshname,
            '{Subject}.R.{map}.{mesh}.shape.gii'.format(**fvars))])
    ## set map meta-data
    run(['wb_command', '-set-map-names', dscalar_file,
        '-map', '1', "{Subject}_{MapName}".format(**fvars)])
    run(['wb_command', '-cifti-palette', dscalar_file,
        mapSettings[MapName]['pallette_mode'], dscalar_file,
        mapSettings[MapName]['pallette_options']])
    ## add to spec file
    run(['wb_command', '-add-to-spec-file',
        os.path.join(meshDict['Folder'],'{Subject}.{mesh}.wb.spec'.format(**fvars)),
        'INVALID', dscalar_file])

def resample_all_dscalars(Subject, RegSphere, current_mesh, dest_mesh,
        meshSettings = meshSettings, mapSettings = dscalarSettings):
    ''' loops over all metrics in the dscalarSettings '''
    for MapName in mapSettings.keys():
        for Hemisphere in ['L','R']:
            resample_and_mask_metric(RegSphere, current_mesh, dest_mesh,
                    Subject, Hemisphere, MapName)
        create_dscalar_add_to_spec(dest_mesh, MapName, Subject)

def copy_colin_flat_and_add_to_spec(SurfaceAtlasDIR, AtlasSpaceFolder,
        Subject, Hemisphere, MeshRes, spec_file, Structure):
    ''' copy the colin flat atlas out of the templates folder and add it to the spec file'''
    colin_src = os.path.join(SurfaceAtlasDIR,
        'colin.cerebral."$Hemisphere".flat."$LowResMesh"k_fs_LR.surf.gii'.format(Hemisphere, MesRes))
    if os.file.exists(colin_src):
        colin_dest = os.path.join(AtlasSpaceFolder,'fsaverage_LR()k'.format(MeshRes),
            '{}.{}.flat.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, MesRes))
        run(['cp', colin_src colin_dest])
        run(['wb_command', '-add-to-spec-file', spec_file, Structure, colin_dest])

def run_MSMSulc_registration():
        sys.exit('Sorry, MSMSulc registration is not ready yet...Exiting')
#   #If desired, run MSMSulc folding-based registration to FS_LR initialized with FS affine
#   if [ ${RegName} = "MSMSulc" ] ; then
#     #Calculate Affine Transform and Apply
#     if [ ! -e "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc ] ; then
#       mkdir "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc
#     fi
#     ${CARET7DIR}/wb_command -surface-affine-regression "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.native.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.reg.reg_LR.native.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.mat
#     ${CARET7DIR}/wb_command -surface-apply-affine "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.native.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.mat "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.sphere_rot.surf.gii
#     ${CARET7DIR}/wb_command -surface-modify-sphere "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.sphere_rot.surf.gii 100 "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.sphere_rot.surf.gii
#     cp "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.sphere_rot.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.rot.native.surf.gii
#     DIR=`pwd`
#     cd "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc
#     #Register using FreeSurfer Sulc Folding Map Using MSM Algorithm Configured for Reduced Distortion
#     #${MSMBin}/msm --version
#     ${MSMBin}/msm --levels=4 --conf=${MSMBin}/allparameterssulcDRconf --inmesh="$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.rot.native.surf.gii --trans="$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.rot.native.surf.gii --refmesh="$AtlasSpaceFolder"/"$Subject"."$Hemisphere".sphere."$HighResMesh"k_fs_LR.surf.gii --indata="$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sulc.native.shape.gii --refdata="$SurfaceAtlasDIR"/"$Hemisphere".refsulc."$HighResMesh"k_fs_LR.shape.gii --out="$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}. --verbose
#     cd $DIR
#     cp "$AtlasSpaceFolder"/"$NativeFolder"/MSMSulc/${Hemisphere}.HIGHRES_transformed.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.surf.gii
#     ${CARET7DIR}/wb_command -set-structure "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.surf.gii ${Structure}
#
#     #Make MSMSulc Registration Areal Distortion Maps
#     ${CARET7DIR}/wb_command -surface-vertex-areas "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".sphere.native.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".sphere.native.shape.gii
#     ${CARET7DIR}/wb_command -surface-vertex-areas "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.surf.gii "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.shape.gii
#     ${CARET7DIR}/wb_command -metric-math "ln(spherereg / sphere) / ln(2)" "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".ArealDistortion_MSMSulc.native.shape.gii -var sphere "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".sphere.native.shape.gii -var spherereg "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.shape.gii
#     rm "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".sphere.native.shape.gii "$AtlasSpaceFolder"/"$NativeFolder"/${Subject}.${Hemisphere}.sphere.MSMSulc.native.shape.gii
#     ${CARET7DIR}/wb_command -set-map-names "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".ArealDistortion_MSMSulc.native.shape.gii -map 1 "$Subject"_"$Hemisphere"_Areal_Distortion_MSMSulc
#     ${CARET7DIR}/wb_command -metric-palette "$AtlasSpaceFolder"/"$NativeFolder"/"$Subject"."$Hemisphere".ArealDistortion_MSMSulc.native.shape.gii MODE_AUTO_SCALE -palette-name ROY-BIG-BL -thresholding THRESHOLD_TYPE_NORMAL THRESHOLD_TEST_SHOW_OUTSIDE -1 1
#
#     RegSphere="${AtlasSpaceFolder}/${NativeFolder}/${Subject}.${Hemisphere}.sphere.MSMSulc.native.surf.gii"



logger.info("Platform Information Follows: ")
#add my config info

logger.info("Parsing Command Line Options")

logger.info('freesurfer SUBJECTS_DIR: {}'.format(SUBJECTS_DIR))
logger.info('HCP_DATA directory: {}'.format(HCP_DATA))
logger.info('Subject: {}'.format(Subject))


logger.info("START: FS2CaretConvertRegisterNonlinear")

###Templates and settings
BrainSize = "150" #BrainSize in mm, 150 for humans
FNIRTConfig = os.path.join(ciftify.config.find_fsl(),'etc','flirtsch','T1_2_MNI152_2mm.cnf') #FNIRT 2mm T1w Config
T1wTemplate2mmBrain = os.path.join(ciftify.config.find_fsl(),'data', 'standard', 'MNI152_T1_2mm_brain.nii.gz') #Hires brain extracted MNI template
T1wTemplate2mm = os.path.join(ciftify.config.find_fsl(),'data', 'standard','MNI152_T1_2mm.nii.gz') #Lowres T1w MNI template
T1wTemplate2mmMask = os.path.join(ciftify.config.find_fsl(),'data', 'standard', 'MNI152_T1_2mm_brain_mask_dil.nii.gz') #Lowres MNI brain mask template
FreeSurferLabels = os.path.join(find_ciftify_templates(),'hcp_config','FreeSurferAllLut.txt')
GrayordinatesSpaceDIR = os.path.join(find_ciftify_templates(),'91282_Greyordinates')
SubcorticalGrayLabels = os.path.join(find_ciftify_templates(),'FreeSurferSubcorticalLabelTableLut.txt')
SurfaceAtlasDIR = os.path.join(find_ciftify_templates(),'standard_mesh_atlases')

### Naming conventions
T1wFolder = os.path.join(HCP_DATA, Subject, 'T1w')
AtlasSpaceFolder = os.path.join(HCP_DATA, Subject, 'MNINonLinear')

FreeSurferFolder= os.path.join(SUBJECTS_DIR,Subject)
GrayordinatesResolutions = "2"
HighResMesh = "164"
LowResMeshes = ["32"]
NativeFolder = "Native"
RegName = "FS"

T1wImageBrainMask="brainmask_fs"
T1w_nonacpc="T1w_noacpc"
T1wImage="T1w" #if not running
T1wImageBrain="${T1wImage}_brain"

#Make some folders for this and later scripts
run(['mkdir','p',os.path.join(T1wFolder,NativeFolder)])
run(['mkdir','p',os.path.join(AtlasSpaceFolder,NativeFolder)])
run(['mkdir','p',os.path.join(AtlasSpaceFolder,'xfms')])
run(['mkdir','p',os.path.join(AtlasSpaceFolder,'ROIs')])
run(['mkdir','p',os.path.join(AtlasSpaceFolder,'Results')])
run(['mkdir','p',os.path.join(T1wFolder,'fsaverage')])
run(['mkdir','p',os.path.join(AtlasSpaceFolder,'fsaverage')])
for LowResMesh in LowResMeshes:
  run(['mkdir','p',os.path.join(T1wFolder,'fsaverage_LR{}k'.format(LowResMesh))])
  run(['mkdir','p',os.path.join(AtlasSpaceFolder,'fsaverage_LR{}k'.format(LowResMesh))])

## the ouput files
T1w_nii = os.path.join(T1wFolder,'{}.nii.gz'.format(T1wImage))
T1wImageBrainMask = os.path.join(T1wFolder,"brainmask_fs.nii.gz")
T1wBrain_nii = os.path.join(T1wFolder,'{}_brain.nii.gz'.format(T1wImage))
AtlasTransform_Linear = os.path.join(AtlasSpaceFolder,'xfms','T1w2StandardLinear.mat')
AtlasTransform_NonLinear = os.path.join(AtlasSpaceFolder,'T1w2Standard_warp_noaffine.nii.gz')
InverseAtlasTransform_NonLinear = os.path.join(AtlasSpaceFolder,'xfms', 'Standard2T1w_warp_noaffine.nii.gz')
T1wImage_MNI = os.path.join(AtlasSpaceFolder,'{}.nii.gz'.format(T1wImage))

###### convert the mgz T1w and put in T1w folder
run(['mri_convert', os.path.join(FreeSurferFolder,'mri','T1.mgz'), T1w_nii])
run(['fslreorient2std', T1w_nii, T1w_nii])

#Convert FreeSurfer Volumes and import the label metadata
for Image in ['wmparc', 'aparc.a2009s+aseg', 'aparc+aseg']:
  if os.path.isfile(os.path.join(FreeSurferFolder,'mri','{}.mgz'.format(Image))):
    run(['mri_convert', '-rt', 'nearest',
      '-rl', T1w_nii,
      os.path.join(FreeSurferFolder,'mri','{}.mgz'.format(Image)),
      os.path.join(T1wFolder,'{}.nii.gz'.format(Image))])
    run(['wb_command', '-volume-label-import',
      os.path.join(T1wFolder,'{}.nii.gz'.format(Image)),
      FreeSurferLabels,
      os.path.join(T1wFolder,'{}.nii.gz'.format(Image)),
      '-drop-unused-labels'])

## Create FreeSurfer Brain Mask skipping 1mm version...
run(['fslmaths',
  os.path.join(T1wFolder,'wmparc.nii.gz'),
  '-bin', '-dilD', '-dilD', '-dilD', '-ero', '-ero',
  T1wImageBrainMask])
run(['wb_command', '-volume-fill-holes', T1wImageBrainMask, T1wImageBrainMask])
run(['fslmaths', T1wImageBrainMask, '-bin', T1wImageBrainMask])
## apply brain mask to the T1wImage
run(['fslmaths', T1w_nii, '-mul', T1wImageBrainMask, T1wBrain_nii])

##### Linear then non-linear registration to MNI
T1w2StandardLinearImage = os.path.join(tmpdir, 'T1w2StandardLinearImage.nii.gz')
run(['flirt', '-interp', 'spline', '-dof', '12',
  '-in', T1wBrain_nii,
  '-ref', T1wTemplate2mmBrain,
  '-omat', AtlasTransform_Linear,
  '-o', T1w2StandardLinearImage])

### calculate the just the warp for the surface transform - need it because sometimes the brain is outside the bounding box of warfield
run(['fnirt',
   '--in={}'.format(T1w2StandardLinearImage),
   '--ref={}'.format(T1wTemplate2mm),
   '--refmask={}'.format(T1wTemplate2mmMask),
   '--fout={}'.format(AtlasTransform_NonLinear),
   '--logout={}'.format(os.path.join(AtlasSpaceFolder,'xfms', 'NonlinearReg_fromlinear.txt')),
   '--config={}'.format(FNIRTConfig)])

## also inverse the non-prelinear warp - we will need it for the surface transforms
run(['invwarp',
  '-w', AtlasTransform_NonLinear,
  '-o', InverseAtlasTransform_NonLinear,
  '-r', T1wTemplate2mm])

##T1w set of warped outputs (brain/whole-head + restored/orig)
run(['applywarp', '--rel', '--interp=trilinear',
  '-i', T1wImage_nii,
  '-r', T1wTemplate2mm,
  '-w', AtlasTransform_NonLinear,
  '--premat={}'.format(AtlasTransform_Linear),
  '-o', T1wImage_MNI])

#Convert FreeSurfer Segmentations to MNI space
for Image in ['wmparc', 'aparc.a2009s+aseg', 'aparc+aseg', 'brainmask_fs']:
  if os.path.isfile(os.path.join(T1wFolder,'{}.nii.gz'.format(Image))):
    Image_MNI = os.path.join(AtlasSpaceFolder,'{}.nii.gz'.format(Image))
    run(['applywarp', '--rel', '--interp=nn',
    '-i', os.path.join(T1wFolder,'{}.nii.gz'.format(Image)),
    '-r', T1wImage_MNI, '-w', AtlasTransform_NonLinear,
    '--premat={}'.format(AtlasTransform_Linear),
    '-o', Image_MNI])
    run(['wb_command', '-volume-label-import',
      Image_MNI, FreeSurferLabels, Image_MNI, '-drop-unused-labels'])

## define the spec file paths
t1w_Native_spec = os.path.join(T1wFolder,NativeFolder, '{}.native.wb.spec'.format(Subject))
MNI_Native_spec = os.path.join(AtlasSpaceFolder,NativeFolder, '{}.native.wb.spec'.format(Subject))
MNI_HighRes_spec = os.path.join(AtlasSpaceFolder,'{}.{}k_fs_LR.wb.spec'.format(Subject,HighResMesh))

#Create Spec Files with the T1w files including
run(['wb_command', '-add-to-spec-file', t1w_native_spec, 'INVALID', T1wImage_nii])
run(['wb_command', '-add-to-spec-file', MNI_native_spec, 'INVALID', T1wImage_MNI])
run(['wb_command', '-add-to-spec-file', MNI_HighRes_spec,'INVALID', T1wImage_MNI])

for LowResMesh in LowResMeshes:
  run(['wb_command', '-add-to-spec-file',
   os.path.join(AtlasSpaceFolder,
                'fsaverage_LR{}k'.format(LowResMesh),
                '{}.{}k_fs_LR.wb.spec'.format(Subject, LowResMesh)),
   'INVALID', T1wImage_MNI])
  run(['wb_command', '-add-to-spec-file',
    os.path.join(T1wFolder,
                 'fsaverage_LR{}k'.format(LowResMesh),
                 '{}.{}k_fs_LR.wb.spec'.format(Subject, LowResMesh)),
    'INVALID', T1wImage_nii])

# Import Subcortical ROIs and resample to the Grayordinate Resolution
for GrayordinatesResolution in GrayordinatesResolutions:
  ## The outputs of this sections
  Atlas_ROIs = os.path.join(AtlasSpaceFolder,'ROIs', 'Atlas_ROIs.{}.nii.gz'.format(GrayordinatesResolution))
  wmparc_ROIs = os.path.join(tmpdir, 'wmparc.{}.nii.gz'.format(GrayordinatesResolution))
  wmparcAtlas_ROIs = os.path.join(tmpdir, 'Atlas_wmparc.{}.nii.gz'.format(GrayordinatesResolution))
  ROIs_nii = os.path.join(AtlasSpaceFolder, 'ROIs', 'ROIs.{}.nii.gz'.format(GrayordinatesResolution))
  T1wImage_res = os.path.join(AtlasSpaceFolder, 'T1w.{}.nii.gz'.format(GrayordinatesResolution))
  ## the analysis steps
  run(['cp',
    os.path.join(GrayordinatesSpaceDIR, 'Atlas_ROIs.{}.nii.gz'.format(GrayordinatesResolution)),
    Atlas_ROIs])
  run(['applywarp', '--interp=nn',
    '-i', os.path.join(AtlasSpaceFolder, 'wmparc.nii.gz'),
    '-r', Atlas_ROIs, '-o', wmparc_ROIs])
  run(['wb_command', '-volume-label-import',
    wmparc_ROIs, FreeSurferLabels, wmparc_ROIs, '-drop-unused-labels'])
  run(['applywarp', '--interp=nn',
    '-i', os.path.join(SurfaceAtlasDIR, 'Avgwmparc.nii.gz'),
    '-r', Atlas_ROIs, '-o', wmparcAtlas_ROIs])
  run(['wb_command', '-volume-label-import',
    wmparcAtlas_ROIs, FreeSurferLabels,  wmparcAtlas_ROIs, '-drop-unused-labels'])
  run(['wb_command', '-volume-label-import',
    wmparc_ROIs, SubcorticalGrayLabels, ROIs_nii,'-discard-others'])
  run(['applywarp', '--interp=spline',
    '-i', T1wImage_MNI, '-r', Atlas_ROIs,
    '-o', T1wImage_res])

#Find c_ras offset between FreeSurfer surface and volume and generate matrix to transform surfaces
cras_mat = write_cras_file(FreeSurferFolder)

#Loop through left and right hemispheres
for Hemisphere, hemisphere, Structure in [('L','l','CORTEX_LEFT'), ('R','r', 'CORTEX_RIGHT')]:

  #native Mesh Processing
  #Convert and volumetrically register white and pial surfaces makign linear and nonlinear copies, add each to the appropriate spec file
  SurfDict = {
    'white' : { Type : 'ANATOMICAL', Secondary : '-surface-secondary-type GRAY_WHITE' },
    'pial' :  { Type : 'ANATOMICAL', Secondary : '-surface-secondary-type PIAL' }}

  for Surface in ['white', 'pial'] :
    surf_fs = os.path.join(FreeSurferFolder,'surf','{}h.{}'.format(hemisphere, Surface))
    surf_native = os.path.join(T1wFolder,NativeFolder,'{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface))
    surf_mni = os.path.join(AtlasSpaceFolder, NativeFolder, '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface))
    ## convert the surface into the T1w/Native Folder
    run(['mris_convert',surf_fs, surf_native])
    run(['wb_command', '-set-structure', surf_native, Structure,
      '-surface-type', SurfDict[Surface]['Type'], SurfDict[Surface]['Secondary']])
    run(['wb_command', '-surface-apply-affine', surf_native,
      cras_mat, surf_native])
    run(['wb_command', '-add-to-spec-file',t1w_Native_spec,Structure, surf_native])
    ## MNI transform the surfaces into the MNINonLinear/Native Folder
    run(['wb_command', '-surface-apply-affine',
      surf_native, AtlasTransform_Linear, surf_mni,
      '-flirt', T1w_nii, T1wTemplate2mm])
    run(['wb_command', '-surface-apply-warpfield',
      surf_mni, InverseAtlasTransform_NonLinear, surf_mni,
      '-fnirt', AtlasTransform_NonLinear ])
    run(['wb_command', '-add-to-spec-file', MNI_Native_spec, Structure, surf_mni ])

  #Create midthickness by averaging white and pial surfaces and use it to make inflated surfacess
  for Folder in [T1wFolder, AtlasSpaceFolder]:
    ## the spec files for this section
    spec_file = os.path.join(Folder,NativeFolder,'{}.native.wb.spec'.format(Subject))
    #Create midthickness by averaging white and pial surfaces
    mid_surf = os.path.join(Folder,NativeFolder,'{}.{}.midthickness.native.surf.gii'.format(Subject, Hemisphere))
    run(['wb_command', '-surface-average', mid_surf,
      '-surf', os.path.join(Folder,NativeFolder,'{}.{}.white.native.surf.gii'.format(Subject, Hemisphere)),
      '-surf', os.path.join(Folder,NativeFolder,'{}.{}.pial.native.surf.gii'.format(Subject. Hemisphere))])
    run(['wb_command', '-set-structure', mid_surf, Structure,
      '-surface-type', 'ANATOMICAL', '-surface-secondary-type', 'MIDTHICKNESS'])
    run(['wb_command', '-add-to-spec-file', spec_file, Structure, mid_surf])
    # make inflated surfaces
    make_inflated_surfaces(mid_surf, spec_file, Structure)

  #Convert original and registered spherical surfaces and add them to the nonlinear spec file
  for Surface in ['sphere.reg', 'sphere']:
    run(['mris_convert',
        os.path.join(FreeSurferFolder,'surf','{}h.{}'.format(hemisphere,Surface)),
        os.path.join(AtlasSpaceFolder,NativeFolder,
            '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface))])
    run(['wb_command', '-set-structure',
        os.path.join(AtlasSpaceFolder,NativeFolder,
            '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface)),
        Structure, '-surface-type', 'SPHERICAL'])
  run(['wb_command', '-add-to-spec-file',
    MNI_Native_spec, Structure,
    os.path.join(AtlasSpaceFolder,NativeFolder,
        '{}.{}.sphere.native.surf.gii'.format(Subject, Hemisphere))])

  #Add more files to the spec file and convert other FreeSurfer surface data to metric/GIFTI including sulc, curv, and thickness.

  for wbname in dscalarSettings.keys():
      if 'fsname' in dscalarSettings[wbname].keys():
    fsname = dscalarSettings[wbname]['fsname']
    postfix = dscalarSettings[wbname]['postfix']
    mapname = MapDict['mapname']
    map_native_gii = os.path.join(tmpdir,'native','{}.{}.{}.native.shape.gii'.format(Subject, Hemisphere, wbname))
    ## convert the freesurfer files to gifti
    run(['mris_convert', '-c',
        os.path.join(FreeSurferFolder,'surf','{}h.{}'.format(hemisphere, fsname)),
        os.path.join(FreeSurferFolder,'surf', '{}h.white'.format(hemisphere)),
        map_native_gii])
    ## set a bunch of meta-data and multiply by -1
    run(['wb_command', '-set-structure',map_native_gii, Structure])
    run(['wb_command', '-metric-math', '(var * -1)',
        map_native_gii, '-var', 'var', map_native_gii])
    run(['wb_command', '-set-map-names', map_native_gii,
        '-map', '1', '{}_{}{}'.format(Subject, Hemisphere, postfix)])
    run(['wb_command', '-metric-palette', map_native_gii, 'MODE_AUTO_SCALE_PERCENTAGE',
        '-pos-percent', '2', '98',
        '-palette-name', 'Gray_Interp',
        '-disp-pos', 'true', '-disp-neg', 'true', '-disp-zero', 'true'])

  #Thickness set thickness at absolute value than set palette metadata
  thickness_native_gii = os.path.join(tmpdir, 'native',
    '{}.{}.thickness.native.shape.gii'.format(Subject,Hemisphere))
  run(['wb_command', '-metric-math', '(abs(thickness))',
    thickness_native_gii, '-var', 'thickness', thickness_native_gii])
  run(['wb_command', '-metric-palette', thickness_native_gii,
    'MODE_AUTO_SCALE_PERCENTAGE', '-pos-percent', '4', '96',
    '-interpolate', 'true', '-palette-name', 'videen_style',
    '-disp-pos', 'true', '-disp-neg', 'false', '-disp-zero', 'false'])

  ## create the native ROI file using the thickness file
  thickness_roi =  os.path.join(AtlasSpaceFolder,NativeFolder,
    '{}.{}.roi.native.shape.gii'.format(Subject, Hemisphere))
  midthickness_gii = os.path.join(AtlasSpaceFolder, NativeFolder,
      '{}.{}.midthickness.native.surf.gii'.format(Subject, Hemisphere))
  run(['wb_command', '-metric-math', "(thickness > 0)",
    thickness_roi, '-var', 'thickness', thickness_native_gii])
  run(['wb_command', '-metric-fill-holes',
    midthickness_gii, thickness_roi, thickness_roi])
  run(['wb_command', '-metric-remove-islands',
    midthickness_gii, thickness_roi, thickness_roi])
  run(['wb_command', '-set-map-names', thickness_roi,
    '-map', '1', '{}_{}_ROI'.format(Subject, Hemisphere)])

  ## dilate the thickness and curvature file by 10mm
  run(['wb_command', '-metric-dilate', thickness_native_gii,
    midthickness_gii, '10', thickness_native_gii, '-nearest'])
  curv_native_gii = os.path.join(tmpdir,'native',
      '{}.{}.curvature.native.shape.gii'.format(Subject,Hemisphere))
  run(['wb_command', '-metric-dilate', curv_native_gii,
    midthickness_gii, '10', curv_native_gii, '-nearest'])

  # Convert freesurfer annotation to gift labels and set meta-data
  for Map in ['aparc', 'aparc.a2009s', 'BA']:
      fs_annot = os.path.join(FreeSurferFolder,'label',
      '{}h.{}.annot'.format(hemisphere, Map))
      if os.file.exists(fs_annot):
          label_gii = os.path.join(tmpdir,'native',
            '{}.{}.{}.native.label.gii'.format(Subject, Hemisphere, Map))
          run(['mris_convert', '--annot', fs_annot,
            os.path.join(FreeSurferFolder,'surf','{}h.white'.format(hemisphere)),
            label_gii])
          run(['wb_command', '-set-structure', label_gii, 'Structure'])
          run(['wb_command', '-set-map-names', label_gii,
            '-map', '1', '{}_{}_{}'.format(Subject,Hemisphere,Map)])
          run(['wb_command', '-gifti-label-add-prefix',
            label_gii, '{}_'.format(Hemisphere), label_gii])
  #End main native mesh processing

for Hemisphere, hemisphere, Structure in [('L','l','CORTEX_LEFT'), ('R','r', 'CORTEX_RIGHT')]:


  #Concatinate FS registration to FS --> FS_LR registration
  run(['wb_command', '-surface-sphere-project-unproject',
    os.path.join([AtlasSpaceFolder,NativeFolder,
        '{}.{}.sphere.reg.native.surf.gii'.format(Subject, Hemisphere))
    os.path.join(SurfaceAtlasDIR, 'fs_{}'.format(Hemisphere),
        'fsaverage.{0}.sphere.{1}k_fs_{0}.surf.gii'.format(Hemisphere, HighResMesh)),
    os.path.join(SurfaceAtlasDIR, 'fs_{}'.format(Hemisphere),
        'fs_{0}-to-fs_LR_fsaverage.{0}_LR.spherical_std.{1}k_fs_{0}.surf.gii'.format(Hemisphere, HighResMesh)),
    os.path.join(AtlasSpaceFolder,NativeFolder,
        '{}.{}.sphere.reg.reg_LR.native.surf.gii'.format(Subject, Hemisphere))])

  #Make FreeSurfer Registration Areal Distortion Maps
  calc_ArealDistortion_gii(
    os.path.join([AtlasSpaceFolder,NativeFolder,
      '{}.{}.sphere.native.surf.gii'.format(Subject, Hemisphere)),
    os.path.join([AtlasSpaceFolder,NativeFolder,
      '{}.{}.sphere.reg.reg_LR.native.surf.gii'.format(Subject, Hemisphere)),
    os.path.join(tmpdir,'native',
        '{}.{}.ArealDistortion_FS.native.shape.gii'.format(Subject, Hemisphere)),
    '{}_{}'.format(Subject, Hemisphere), 'FS')

    if RegName == 'MSMSulc':
        run_MSMSulc_registration()
    else :
     RegSphere = os.path.join(AtlasSpaceFolder,NativeFolder,
        '{}.{}.sphere.reg.reg_LR.native.surf.gii'.format(Subject, Hemisphere))

  #Ensure no zeros in atlas medial wall ROI
  atlasroi_native_gii = os.path.join(AtlasSpaceFolder,NativeFolder,
      '{}.{}.atlasroi.native.shape.gii'.format(Subject, Hemisphere))
  run(['wb_command', '-metric-resample',
    os.path.join(SurfaceAtlasDIR,
        '{}.atlasroi.{}k_fs_LR.shape.gii'.format(Hemisphere, HighResMesh)),
    highres_sphere_gii, RegSphere, 'BARYCENTRIC',
    atlasroi_native_gii,'-largest'])
  run(['wb_command', '-metric-math', '(atlas + individual) > 0)',
    thickness_roi,
    '-var', 'atlas', atlasroi_native_gii,
    '-var', 'individual', thickness_roi)
  ## apply the medial wall roi to the thickness and curvature files
  run(['wb_command', '-metric-mask',
    thickness_native_gii, thickness_roi, thickness_native_gii])
  run(['wb_command', '-metric-mask',
    curv_native_gii, thickness_roi, curv_native_gii])

## mapping native to HighReshMesh
for Hemisphere, hemisphere, Structure in [('L','l','CORTEX_LEFT'), ('R','r', 'CORTEX_RIGHT')]:  #Populate Highres fs_LR spec file.

  ## Copying sphere surface from templates file to subject folder
  highres_sphere_gii = os.path.join(AtlasSpaceFolder,
    '{}.{}.sphere.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, HighResMesh))
  run(['cp',
    os.path.join(SurfaceAtlasDIR,
        'fsaverage.{}_LR.spherical_std.{}k_fs_LR.surf.gii'.format(Hemisphere, HighResMesh)),
    highres_sphere_gii])
  run(['wb_command', '-add-to-spec-file', MNI_HighRes_spec, Structure, highres_sphere_gii])


  ## copying flat surface from templates to subject folder
  copy_colin_flat_and_add_to_spec(SurfaceAtlasDIR, AtlasSpaceFolder,
            Subject, Hemisphere, HighResMesh, MNI_HighRes_spec, Structure)
  # Deform surfaces and other data according to native to folding-based registration selected above.
  # Regenerate inflated surfaces.
  for Surface in ['white', 'midthickness', 'pial']:
    resample_surf_and_add_to_spec(
        surf_in = os.path.join(AtlasSpaceFolder,NativeFolder,
            '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface)),
        surf_out = os.path.join(AtlasSpaceFolder,
            '{}.{}.{}.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, Surface, HighResMesh)),
        current_sphere = RegSphere, new_sphere = highres_sphere_gii,
        spec_file = MNI_HighRes_spec, spec_structure = Structure)

  ## create the inflated HighRes surfaces
  mid_HighRes_surf = os.path.join(AtlasSpaceFolder,
    '{}.{}.midthickness.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere,HighResMesh))
  make_inflated_surfaces(mid_HighRes_surf, MNI_HighRes_spec, Structure)

  for Map in ['aparc', 'aparc.a2009s', 'BA']:
      label_in = os.path.join(tmpdir,'native',
        '{}.{}.{}.native.label.gii'.format(Subject Hemisphere, Map))
      if  os.file.exists(label_in):
          label_out = os.path.join(tmpdir, '{}k_fs_LR'.HighResMesh,
            '{}.{}.{}.{}k_fs_LR.label.gii'.format(Subject, Hemisphere, Map, HighResMesh))
          run(['wb_command', '-label-resample', label_in,
            RegSphere, highres_sphere_gii, 'BARYCENTRIC', label_out, '-largest'])

resample_all_dscalars(Subject, RegSphere, 'native', 'fsaverage_LR{}k'.format(HighResMesh))

### mapping to LowReshMesh spaces
for LowResMesh in LowResMeshes:

    for Hemisphere, hemisphere, Structure in [('L','l','CORTEX_LEFT'), ('R','r', 'CORTEX_RIGHT')]:

        # Set Paths for this section
        AtlasLowReshDir = os.path.join(AtlasSpaceFolder, 'fsaverage_LR{}k'.format(LowResMesh))
        sphere_reg_LowRes = os.path.join(AtlasLowReshDir,
            '{}.{}.sphere.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, LowResMesh))
        MNI_LowRes_spec = os.path.join(AtlasLowReshDir,
            '{}.{}k_fs_LR.wb.spec'.format(Subject, LowResMesh))
        atlasroi_LowRes = os.path.join(AtlasLowReshDir,
            '{}.{}.atlasroi.{}k_fs_LR.shape.gii'.format(Subject, Hemisphere, LowResMesh))
        mid_surf_LowRes = os.path.join(AtlasLowReshDir,
            '{}.{}.midthickness.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, LowResMesh))

        run(['cp', os.path.join(SurfaceAtlasDIR,
            '{}.sphere.{}k_fs_LR.surf.gii'.format(Hemisphere, LowResMesh)),
            sphere_reg_LowRes])
        run(['wb_command', '-add-to-spec-file',
            MNI_LowRes_spec, Structure, sphere_reg_LowRes])
        run(['cp', os.path.join(GrayordinatesSpaceDIR,
            '{}.atlasroi.{}k_fs_LR.shape.gii'.format(Hemisphere, LowResMesh))
            atlasroi_LowRes])
        copy_colin_flat_and_add_to_spec(SurfaceAtlasDIR, AtlasSpaceFolder,
                Subject, Hemisphere, LowResMesh, MNI_LowRes_spec, Structure)

        #Create downsampled fs_LR spec files.
        for Surface in ['white', 'pial']:
            resample_surf_and_add_to_spec(
                surf_in = os.path.join(AtlasSpaceFolder,NativeFolder,
                    '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface)),
                surf_out = os.path.join(AtlasSpaceFolder,
                    '{}.{}.{}.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, Surface, LowResMesh)),
                current_sphere = RegSphere, new_sphere = sphere_reg_LowRes,
                spec_file = MNI_LowRes_spec, spec_structure = Structure)

        resample_surf_and_add_to_spec(
            surf_in = midthickness_gii, surf_out = mid_surf_LowRes,
            current_sphere = RegSphere, new_sphere = sphere_reg_LowRes,
            spec_file = MNI_LowRes_spec, spec_structure = Structure)

        make_inflated_surfaces(mid_surf_LowRes,
            MNI_LowRes_spec, Structure, iterations_scale = 0.75)

        for Map in ['aparc', 'aparc.a2009s', 'BA']:
          label_in = os.path.join(tmpdir,'native',
            '{}.{}.{}.native.label.gii'.format(Subject Hemisphere, Map))
          if  os.file.exists(label_in):
              label_out = os.path.join(tmpdir, 'fsaverage_LR{}k'.format(LowResMesh),
                '{}.{}.{}.{}k_fs_LR.label.gii'.format(Subject, Hemisphere, Map, LowResMesh))
              run(['wb_command', '-label-resample', label_in,
                RegSphere, sphere_reg_LowRes, 'BARYCENTRIC', label_out, '-largest'])

    resample_all_dscalars(Subject, RegSphere, 'native', 'fsaverage_LR{}k'.format(LowResMesh))

## mapping native to Low Rest T1w space
for Hemisphere, hemisphere, Structure in [('L','l','CORTEX_LEFT'), ('R','r', 'CORTEX_RIGHT')]:
    #Create downsampled fs_LR spec file in structural space.
    T1_LowRes_spec = os.path.join(T1wFolder,'fsaverage_LR"$LowResMesh"k'.format(LowResMesh),
            '{}.{}k_fs_LR.wb.spec'.format(Subject, LowResMesh))
    for Surface in ['white', 'pial', 'midthickness']:
        resample_surf_and_add_to_spec(
            surf_in = os.path.join(T1wFolder,NativeFolder,
                '{}.{}.{}.native.surf.gii'.format(Subject, Hemisphere, Surface)),
            surf_out = os.path.join(T1wFolder,'fsaverage_LR"$LowResMesh"k'.format(LowResMesh),
                '{}.{}.{}.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, Surface, LowResMesh)),
            current_sphere = RegSphere, new_sphere = sphere_reg_LowRes,
            spec_file = MNI_LowRes_spec, spec_structure = Structure)

    resample_surf_and_add_to_spec(
        surf_in = midthickness_gii, surf_out = mid_surf_LowRes,
        current_sphere = RegSphere, new_sphere = sphere_reg_LowRes,
        spec_file = MNI_LowRes_spec, spec_structure = Structure)

    make_inflated_surfaces(
        os.path.join(T1wFolder,'fsaverage_LR{}k'.format(LowResMesh),
            '{}.{}.midthickness.{}k_fs_LR.surf.gii'.format(Subject, Hemisphere, LowResMesh)),
        T1w_LowRes_spec, Structure, iterations_scale = 0.75)
