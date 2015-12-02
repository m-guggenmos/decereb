import itertoolsfrom collections import OrderedDict, Sequencefrom copy import deepcopyfrom inspect import isclass, signaturefrom decereb.estimators import RoiEnsemble, SearchlightEnsemblefrom decereb.masker import DummyMasker, MultiRoiMaskerfrom sklearn.base import BaseEstimatorfrom sklearn.kernel_ridge import KernelRidgefrom decereb.pipeline import AnalysisDef, LinkDef, Chainclass Data:    def __init__(self, data=None, mask=None, labels=None, subjects=None, identifier=None, feature_names=None,                 label_names=None):        self.data = data        self.mask = mask        self.labels = labels        self.subjects = subjects        self.identifier = identifier        self.feature_names = feature_names        self.label_names = label_namesclass DescriptorConcatenator:    def __init__(self, descriptor_dict=None, base_keys=None, con_keys=None):        self.descriptor_dict = descriptor_dict        self.base_descriptors = sum([self.descriptor_dict[k] for k in base_keys], [])        if con_keys is not None:            self.connections = [self.descriptor_dict[i] for i in con_keys]        else:            self.connections = None    def as_list(self):        if self.connections is not None:            n = len(self.connections)            perms = [c for i in range(n + 1) for c in itertools.combinations(range(n), i)]            lst = sum([[tuple([deepcopy(base)] + list(deepcopy(con))) for con in itertools.product(*[self.connections[i] for i in p])]                        for p in perms for base in self.base_descriptors], [])            for l in lst:                if len(l) > 1:                    for i, descriptor in enumerate(l):                        new_identifier = OrderedDict()                        for k in descriptor.identifier.keys():                            new_key = '%s%g_%s' % (descriptor.prefix, i, k.split(descriptor.prefix + '_', 1)[1])                            new_identifier[new_key] = descriptor.identifier[k]                        descriptor.identifier = new_identifier        else:            lst = self.base_descriptors        for i, descriptor in enumerate(lst):            if isinstance(descriptor, Sequence):                for d in descriptor:                    d.identifier['%s_id' % d.prefix] = i            else:                descriptor.identifier['%s_id' % descriptor.prefix] = i        return lstclass MetaDescriptor:    def __init__(self):        self.identifier_exceptions = []        self.iterator_exceptions = []        self.iterator_list = []        self.identifier = None    def build_identifier(self):        identifiers = []        for identifier in self.identifier_list:            if issubclass(identifier.__class__, dict):                identifiers += [(self.prefix + '_' + k, v) for k, v in identifier.items() if k not in self.identifier_exceptions]        self.identifier = OrderedDict(identifiers)        for k, v in self.identifier.items():            if isinstance(v, (list, dict)):                self.identifier[k] = str(v)            elif isclass(v):                self.identifier[k] = str(v).split('.')[-1][:-2]            elif hasattr(v, '__class__') and issubclass(v.__class__, BaseEstimator):                self.identifier[k] = str(v)    def as_list(self):        list_args = sum([[(i, k) for k, v in iterator.items() if isinstance(v, list) and k not in self.iterator_exceptions]                         for i, iterator in enumerate(self.iterator_list)], [])        if True in [len(la) > 0 for la in list_args]:            instances = []            perms = [list(p) for p in                     list(itertools.product(*[[(i, la, j) for j in self.iterator_list[i][la]] for i, la in list_args]))]            for perm in perms:                instance = deepcopy(self)                for p in perm:                    instance.iterator_list[p[0]].update([p[1:]])                instance.build_identifier()                instances.append(instance)        else:            instances = [self]        return instancesclass InputDescriptor(MetaDescriptor):    def __init__(self, name=None, data=None, masker=None, masker_args=None, identifier=None):        super().__init__()        self.data = data        self.prefix = 'in'        if masker is None:            self.masker = DummyMasker        else:            self.masker = masker        if masker_args is None:            self.masker_args = dict()        else:            self.masker_args = masker_args        self.iterator_list = [self.masker_args]        self.iterator_exceptions = ['rois']        self.identifier_list = [dict(name=name), self.data.identifier, self.masker_args, identifier]        self.identifier_exceptions = ['rois', 'mask_img']        self.build_identifier()class FeatureSelectionDescriptor(MetaDescriptor):    def __init__(self, fs_type=None, fs_args=None, identifier=None):        super().__init__()        self.fs_type = fs_type        self.fs_args = fs_args        self.prefix = 'fs'        if fs_args is not None:            self.iterator_list += [self.fs_args]            if 'model_args' in fs_args:                self.iterator_list += [self.fs_args['model_args']]        self.identifier_exceptions = ['model_args']        self.identifier_list = [dict(type=self.fs_type), *self.iterator_list, identifier]        self.build_identifier()class ClassifierDescriptor(MetaDescriptor):    def __init__(self, clf=None, clf_args=None, opt_args=None, identifier=None):        super().__init__()        self.clf = clf        if clf_args is None:            self.clf_args = dict()        else:            self.clf_args = clf_args        if hasattr(self.clf, '_estimator_type') and self.clf._estimator_type in ['regressor', 'classifier']:            if self.clf._estimator_type == 'regressor':                self.regression = True            else:                self.regression = False        # elif hasattr(self.clf, '_estimator_type') and self.clf._estimator_type == 'ensemble' \        #             and 'base_estimator_args' in self.clf_args and 'base_estimator' in self.clf_args['base_estimator_args']:        #     if self.clf_args['base_estimator_args']['base_estimator']._estimator_type == 'regressor':        elif hasattr(self.clf, '_estimator_type') and self.clf._estimator_type == 'ensemble':            if 'base_estimator' in self.clf_args:                if self.clf_args['base_estimator']._estimator_type == 'regressor':                    self.regression = True                else:                    self.regression = False            else:                if signature(self.clf).parameters['base_estimator'].default._estimator_type == 'regressor':                    self.regression = True                else:                    self.regression = False        elif 'regression' in opt_args:            self.regression = opt_args['regression']        else:            raise ValueError('Classifier type is not specified (regression or classification?)')        self.prefix = 'clf'        if opt_args is None:            self.opt_args = dict()        else:            self.opt_args = opt_args        if clf_args is not None:            self.iterator_list += [self.clf_args]        if opt_args is not None:            self.iterator_list += [self.opt_args]        self.iterator_exceptions = ['seed_list']        self.identifier_list = [dict(clf=str(self.clf).split('.')[-1][:-2]), *self.iterator_list,                                dict(regression=self.regression), identifier]        self.identifier_exceptions = ['seed_list']        self.build_identifier()class ChainBuilder:    def __init__(self, dataschemes=None, clfs=None, fss=None):        self.dataschemes = dataschemes        self.clfs = clfs        self.fss = fss    def build_chain(self):        linkdef_list = []        for i, scheme in enumerate(self.dataschemes):            for j, clf in enumerate(self.clfs):                for k, fs in enumerate(self.fss):                    fs_ = fs if isinstance(fs, Sequence) else (fs, )                    if not (issubclass(clf.clf, SearchlightEnsemble) and (True in [f.fs_type is not None for f in fs_] or scheme.data.identifier['data_format'] != 'images')) and \                       not (issubclass(clf.clf, KernelRidge) and ('roi' in [f.fs_type for f in fs_] or ('model' in [f.fs_type for f in fs_] and fs_[[f.fs_type for f in fs_].index('model')].fs_args['model'] == 'nested'))) and \                       not (True in [f.fs_type == 'roi' for f in fs_] and scheme.data.identifier['data_format'] != 'images'):                        analysis_def = AnalysisDef(                            X=scheme.data.data,                            y=scheme.data.labels,                            clf=RoiEnsemble if issubclass(scheme.masker, MultiRoiMasker) else clf.clf,                            clf_args=dict(base_estimator=clf.clf(), base_estimator_args=clf.clf_args, continuous=clf.opt_args['continuous'])                                     if issubclass(scheme.masker, MultiRoiMasker) else clf.clf_args,                            masker=deepcopy(scheme.masker),                            masker_args=deepcopy(scheme.masker_args),                            regression=clf.regression,                            seed_list=clf.opt_args['seed_list'] if 'seed_list' in clf.opt_args else None,                            fs=fs,                            label_names=None if clf.regression else scheme.data.label_names                        )                        if issubclass(scheme.masker, MultiRoiMasker):                            analysis_def.clf_args.update(regression=clf.regression)                        if issubclass(clf.clf, SearchlightEnsemble):                            analysis_def.masker_args.update(searchlight=True)                            analysis_def.clf_args.update(searchlight=True)                            analysis_def.clf_args['base_estimator_args'].update(mask_img=scheme.data.mask)                        linkdef = LinkDef(                            analysis_def=analysis_def,                            db_key=OrderedDict(                                list(scheme.identifier.items()) +                                list(clf.identifier.items()) +                                sum([list(f.identifier.items()) for f in fs_], [])                            ),                            info=dict(subjects=scheme.data.subjects, feature_names=scheme.data.feature_names,                                      seeds=clf.opt_args['seed_list'] if 'seed_list' in clf.opt_args else None)                        )                        linkdef_list.append(linkdef)        return Chain(linkdef_list)