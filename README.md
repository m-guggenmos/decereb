# decereb
High-level interface for sklearn / nilearn, targeted at neuroimaging data analysis. Not even alpha at the moment -- the API is expected to change on a daily basis.

**Simple example:**

```python
from sklearn.svm import SVC
from decereb.chain import SimpleChain
from sklearn.datasets import make_classification

X, y = make_classification()
clf = SVC
# Decereb offers two features for classifier and feature selection parameters:
# 1. Parameters in plain list form [Param1, Param2, .. ParamN] generate N analyses looping over
#    each parameter.
#    In the example below, two analyses are produced, one using an RBF kernel and a second one
#    using a linear kernel.
# 2. Parameters defined as a nested list [[Param1, Param2, .. ParamN]] are iterated over in a
#    nested leave-one-out cross-validation procedure using GridSearchCV, to find the optimal
#    parameter in each fold.
#    In the example below, a gridsearch is performed for the parameter C on the values 0.1 and 1,
#    both for the analysis using an RBF kernel and for the analysis using a linear kernel.
clf_args = dict(kernel=['rbf', 'linear'], C=[[0.1, 1]])

# Here we use a variance-based feature selection and start two analyses with two different
# thresholds. Please note that Decereb expands all permutations of classifier parameters and feature
# selection parameters, i.e. in this case the code produces 2x2=4 analyses.
fs = 'variance'
fs_args = dict(threshold=[0.01, 0.1])

analysis = SimpleChain(data=X, clf=clf, clf_args=clf_args, fs=fs, fs_args=fs_args, labels=y)

# n_jobs_links:  distribute different analyses across n_jobs_links processors
# n_jobs_folds:  distribute cross-validation folds of each analysis across n_jobs_folds processors
# verbose:       increase in order to view more detailed results (e.g. fold-wise results)
# output_path:   directory to store the result
# skip_ioerror:  set True if the analysis chain should continue despite an I/O error when saving the,
#                previous result
# skip_runerror: set True if the analysis chain should continue despite any runtime error in the
#                previous analysis
# detailed_save: save more detailed results (currently undocumented)
result = analysis.run(n_jobs_links=1, n_jobs_folds=1, verbose=1, output_path='/tmp/decereb/',
                      skip_ioerror=False, skip_runerror=False, detailed_save=True)
print('Finished example!')

# Decereb results are stored in a simple SQL-based database (https://dataset.readthedocs.org/),
# which allows easy querying of the results (e.g. SELECT * FROM chain ORDER BY roc_auc_scores)
#
# An exception is if the classifier is searchlight-based, in which case the results are saved as
# nibabel.NiftiImages.
```


**Advanced example:**

```python
from sklearn.svm import SVC
from sklearn.ensemble.forest import RandomForestClassifier
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from decereb.chain import Channel, ClassifierDescriptor, FeatureSelectionDescriptor, \
    SchemeDescriptor, Data, ChainBuilder
from sklearn.datasets import make_classification

# Using a slightly more verbose syntax, we can concatenate permutations of analyses using
# (1) different data, (2) different classifiers and (3) different feature selections.

# First we create two different data sets.
X1, y1 = make_classification()
X2, y2 = make_classification()

# Now we setup a list with three different classifiers by using the ClassifierDescriptor class.
clf_args_SVC = dict(kernel='linear', C=[[0.1, 1]])
clf_args_RF = dict(criterion=['entropy', 'gini'], n_estimators=128)
clfs = [
    ClassifierDescriptor(name='SVC_rbf', clf=SVC, clf_args=clf_args_SVC),
    ClassifierDescriptor(name='RF', clf=RandomForestClassifier, clf_args=clf_args_RF),
    ClassifierDescriptor(name='LDA', clf=LinearDiscriminantAnalysis)
]

# Dito for different feature selections.
fss = [
    FeatureSelectionDescriptor(name='nested', fs_args=dict(model='nested', threshold='median')),
    FeatureSelectionDescriptor(name='variance', fs_args=dict(threshold=0.01))
]

# A 'channel' specifies a (permutational) processing pipeline consisting of feature selections and
# classifiers.
channel = Channel(fss=fss, clfs=clfs)

# The (processing) scheme descriptor glues together the data input and processing pipeline. The
# scoring argument allows passing of performance evaluation metric (see sklearn.metrics).
processing_schemes = [
    SchemeDescriptor(name='data_v1', data=Data(X1, y1), channels=channel, scoring='roc_auc'),
    SchemeDescriptor(name='data_v2', data=Data(X2, y2), channels=channel, scoring='roc_auc')
]

# Build the chain, i.e. all permutations of analyses.
analysis = ChainBuilder(schemes=processing_schemes).build_chain()

# And run..
# In this example the chain contains 16 different analyses ('links').
result = analysis.run(n_jobs_links=1, n_jobs_folds=1, verbose=1, output_path='/tmp/decereb/',
                      skip_ioerror=False, skip_runerror=False, detailed_save=True)
print('Finished example!')
```

**Example for a searchlight analysis:**

```python
import os
import numpy as np
import nibabel
from decereb.chain import SimpleChain, Data
from decereb.estimators.searchlight import SearchLight
from nilearn import datasets
from nilearn.image import index_img
from nilearn._utils import check_niimg_4d
from sklearn.cross_validation import KFold

haxby_dataset = datasets.fetch_haxby_simple()

conditions = np.recfromtxt(haxby_dataset.conditions_target)['f0']
condition_mask = np.logical_or(conditions == b'face', conditions == b'house')
labels = conditions[condition_mask]

fmri_img = nibabel.load(haxby_dataset.func)
fmri_img = index_img(fmri_img, condition_mask)
fmri_img = [img for img in check_niimg_4d(fmri_img, return_iterator=True)]

mask_img = nibabel.load(haxby_dataset.mask)

cv = KFold(len(labels), n_folds=4)
clf_args = dict(mask_img=mask_img, process_mask_img=mask_img, cv=cv, radius=5.6)
data = Data(data=fmri_img, labels=labels)
chain = SimpleChain(clf=SearchLight, clf_args=clf_args, data=data)

root = os.path.dirname(haxby_dataset['session_target'])
output_path = os.path.join(root, 'searchlight.nii')

chain.run(n_jobs_folds=1, verbose=3, output_path=output_path)
```
