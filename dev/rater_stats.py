import os
import random
import shutil
import nibabel
import numpy as np
import pandas as pd
from skimage import measure

def subjectFilter(input):
    if("sub" in input):
        return True
    else:
        return False

#contrasts = ["FLAIR", "ce-T1w", "PD", "T1w", "T2w"]
contrasts = ["T2w"]
deriv_path = "/scratch/ms_brain/_BIDS_sameResolution/derivatives/labels"
#deriv_path = "/scratch/ms_brain/_BIDS/derivatives/labels"
subjects=list(filter(subjectFilter,os.listdir(deriv_path)))
print(subjects)

df = pd.DataFrame(columns = ['file' , 'rater', 'metric' , 'value'])

for subject in subjects:
    files = os.listdir(os.path.join(deriv_path,subject,"anat"))
    niis = [file for file in files if any(contrast in file for contrast in contrasts)]
    for nii in niis:
        base_name = "_".join((nii.split("_"))[0:2])
        rater = ((nii.split("_")[-1]).split(".")[0])[-1]
        if rater.isnumeric():
            fname = os.path.join(deriv_path,subject,"anat",nii)
            im1 = nibabel.load(fname).get_data()
            #Threshold
            im1[im1 > 0] = 1
            #print("unique values",np.unique(im1))
            labels = measure.label(im1)
            #print("lesion count",labels.max())
            df = df.append({'file': base_name, 'rater': rater, 'lesion_count': labels.max(), 'positive_voxels': np.count_nonzero(im1), 'value': 0}, ignore_index=True)
            print(base_name)
            print(rater)

print(df.head(30))
