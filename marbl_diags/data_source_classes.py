""" These classes build on GenericDataSource to open data from specific sources """

import glob
import logging
import os
import json
import xarray as xr
from .generic_classes import GenericDataSource

######################################################################

class CachedClimoData(GenericDataSource):
    """ Class built around reading previously-cached data """
    def __init__(self, data_root, var_dict_in, data_type, **kwargs):
        self._var_dict_in = var_dict_in
        super(CachedClimoData, self).__init__(child_class='CachedClimoData', **kwargs)
        self._get_dataset(data_root, data_type)

    def _get_dataset(self, data_root, data_type):
        self.logger.debug('calling _get_dataset, data_type = %s', data_type)
        self._is_ann_climo = False
        self._is_mon_climo = True
        if data_type == 'zarr':
            self.ds = xr.open_zarr(data_root, decode_times=False, decode_coords=False) # pylint: disable=invalid-name

    def _set_var_dict(self):
        if not os.path.exists(self._var_dict_in):
            raise FileNotFoundError('Can not find %s' % self._var_dict_in)

        self.logger.debug('Getting cached variable dictionary from %s', self._var_dict_in)
        with open(self._var_dict_in) as file_in:
            self._var_dict = json.load(file_in)
        del self._var_dict_in

    def compute_mon_climatology(self):
        """ Cached data should already be climatology """
        pass

######################################################################

class CESMData(GenericDataSource):
    """ Class built around reading CESM history files """
    def __init__(self, variables, operation, datestr_in, **kwargs):
        super(CESMData, self).__init__(child_class='CESMData', **kwargs)
        gdargs = dict()
        gdargs['variables'] = variables
        # Set filetype depending on requested operation
        if operation == "ann_climo":
            if "ann_climo" in kwargs['dataset_format']:
                gdargs['filetype'] = 'ann_climo'
            elif "mon_climo" in kwargs['dataset_format']:
                gdargs['filetype'] = 'mon_climo'
            elif "single_variable" in kwargs['dataset_format']:
                gdargs['filetype'] = 'single_variable'
            else:
                raise ValueError("Can not find appropriate filetype for %s", operation)
        else:
            raise ValueError("'%s' is an unknown operation", operation)
        for key in kwargs['dataset_format'][gdargs['filetype']]:
            gdargs[key] = kwargs['dataset_format'][gdargs['filetype']][key]
        gdargs['case'] = kwargs['case']
        gdargs['datestr'] = datestr_in
        self._get_dataset(**gdargs)
        #-- do unit conversions belong here?
        # maybe there should be a "conform_data_sources" method?
        if 'z_t' in self.ds:
            self.ds['z_t'].values = self.ds['z_t'].values * 1e-2
        if 'Fe' in self.ds:
            self.ds['Fe'].values = self.ds['Fe'].values * 1e6
            #self.ds.Fe.attrs.units = 'pM'

    def compute_mon_climatology(self):
        """ Compute monthly climatology (if necessary) """
        if self._is_mon_climo or self._is_ann_climo:
            return
        super(CESMData, self).compute_mon_climatology()

    def _get_dataset(self, filetype, dirin, case, stream, datestr, variables):
        """ docstring """
        xr_open_ds = {'decode_coords' : False, 'decode_times' : False, 'data_vars' : 'minimal'}
        if isinstance(datestr, str):
            datestr = [datestr]

        if filetype == 'hist':

            self._is_ann_climo = False
            self._is_mon_climo = False
            file_name_pattern = []
            for date_str in datestr:
                file_name_pattern.append('{}/{}.{}.{}.nc'.format(dirin, case, stream, date_str))
            self._list_files(file_name_pattern)

            self.logger.debug('Opening %d files: ', len(self._files))
            for n, file_name in enumerate(self._files): # pylint: disable=invalid-name
                self.logger.debug('%d: %s', n+1, file_name)

            self.ds = xr.open_mfdataset(self._files, **xr_open_ds)

            tb_name = ''
            if 'bounds' in self.ds['time'].attrs:
                tb_name = self.ds['time'].attrs['bounds']
            elif 'time_bound' in self.ds:
                tb_name = 'time_bound'

            static_vars = [v for v, da in self.ds.variables.items()
                           if 'time' not in da.dims]
            self.logger.debug('static vars: %s', static_vars)

            keep_vars = ['time', tb_name]+[var for var in self._var_dict.values()]+static_vars
            self.logger.debug('keep vars: %s', keep_vars)

            drop_vars = [v for v, da in self.ds.variables.items()
                         if 'time' in da.dims and v not in keep_vars]

            self.logger.debug('dropping vars: %s', drop_vars)
            self.ds = self.ds.drop(drop_vars)

        elif filetype in ['mon_climo', 'ann_climo']:

            if filetype == 'mon_climo':
                self._is_ann_climo = False
                self._is_mon_climo = True
            else:
                self._is_ann_climo = True
                self._is_mon_climo = False
            file_name_pattern = []
            for date_str in datestr:
                file_name_pattern.append('{}/{}.{}.nc'.format(dirin, stream, date_str))
            self._list_files(file_name_pattern)

            self.logger.debug('Opening %d files: ', len(self._files))
            for n, file_name in enumerate(self._files): # pylint: disable=invalid-name
                self.logger.debug('%d: %s', n+1, file_name)

            self.ds = xr.open_mfdataset(self._files, **xr_open_ds)

            tb_name = ''
            if 'bounds' in self.ds['time'].attrs:
                tb_name = self.ds['time'].attrs['bounds']
            elif 'time_bound' in self.ds:
                tb_name = 'time_bound'

            static_vars = [v for v, da in self.ds.variables.items()
                           if 'time' not in da.dims]
            self.logger.debug('static vars: %s', static_vars)

            keep_vars = ['time', tb_name]+[var for var in self._var_dict.values()]+static_vars
            self.logger.debug('keep vars: %s', keep_vars)

            drop_vars = [v for v, da in self.ds.variables.items()
                         if 'time' in da.dims and v not in keep_vars]

            self.logger.debug('dropping vars: %s', drop_vars)
            self.ds = self.ds.drop(drop_vars)

        elif filetype == 'single_variable':

            self._is_ann_climo = False
            self._is_mon_climo = False
            self.ds = xr.Dataset()
            for variable in variables:
                file_name_pattern = []
                for date_str in datestr:
                    file_name_pattern.append('{}/{}.{}.{}.{}.nc'.format(
                        dirin, case, stream, self._var_dict[variable], date_str))
                self._list_files(file_name_pattern)
                self.ds = xr.merge((self.ds, xr.open_mfdataset(self._files, **xr_open_ds)))

        else:
            raise ValueError('Unknown format: %s' % filetype)

        # should this method handle making the 'time' variable functional?
        # (i.e., take mean of time_bound, convert to date object)

    def _list_files(self, glob_pattern):
        '''Glob for files and check that some were found.'''

        self._files = []
        for glob_pat in glob_pattern:
            self.logger.debug('glob file search: %s', glob_pat)
            self._files += sorted(glob.glob(glob_pat))
        if not self._files:
            raise ValueError('No files: %s' % glob_pattern)

    def _set_var_dict(self):
        self._var_dict = dict()
        self._var_dict['nitrate'] = 'NO3'
        self._var_dict['phosphate'] = 'PO4'
        self._var_dict['oxygen'] = 'O2'
        self._var_dict['silicate'] = 'SiO3'
        self._var_dict['dic'] = 'DIC'
        self._var_dict['alkalinity'] = 'ALK'
        self._var_dict['iron'] = 'Fe'

######################################################################

class WOAData(GenericDataSource):
    """ Class built around reading World Ocean Atlas 2013 reanalysis """
    def __init__(self, var_dict, **kwargs):
        super(WOAData, self).__init__(child_class='WOAData', **kwargs)
        self._set_woa_names()
        gdargs = dict()
        gdargs['freq'] = 'ann'
        climo_type = '{}_climo'.format(gdargs['freq'])
        gdargs['grid'] = kwargs['grid']
        gdargs['dirin'] = kwargs[climo_type]['dirin']
        if 'filename' in kwargs[climo_type]:
            gdargs['filename'] = kwargs[climo_type]['filename']
        self._get_dataset(var_dict, **gdargs)
        #-- do unit conversions belong here?
        # maybe there should be a "conform_data_sources" method?
        if 'z_t' in self.ds:
            if self.ds.z_t.attrs['units'] in ['centimeters', 'cm']:
                self.ds.z_t.values = self.ds.z_t.values * 1e-2

    def _set_woa_names(self):
        """ Define the _woa_names dictionary """
        # self.woa_names = {'T':'t', 'S':'s', 'NO3':'n', 'O2':'o', 'O2sat':'O', 'AOU':'A',
        #                   'SiO3':'i', 'PO4':'p'}
        self._woa_names = dict()
        self._woa_names['nitrate'] = 'n'
        self._woa_names['phosphate'] = 'p'
        self._woa_names['oxygen'] = 'o'
        self._woa_names['silicate'] = 'i'
        # self._woa_names['dic'] = 'none'
        # self._woa_names['alkalinity'] = 'none'

    def _set_var_dict(self):
        self._var_dict = dict()
        self._var_dict['nitrate'] = 'NO3'
        self._var_dict['phosphate'] = 'PO4'
        self._var_dict['oxygen'] = 'O2'
        self._var_dict['silicate'] = 'SiO3'
        # self._var_dict['dic'] = 'DIC'
        # self._var_dict['alkalinity'] = 'ALK'

    def _get_dataset(self, var_dict, dirin, freq='ann', grid='1x1d', filename=None):
        """ docstring """
        mlperl_2_mmolm3 = 1.e6 / 1.e3 / 22.3916
        long_names = {'NO3':'Nitrate', 'O2':'Oxygen', 'O2sat':'Oxygen saturation', 'AOU':'AOU',
                      'SiO3':'Silicic acid', 'PO4':'Phosphate', 'S':'Salinity', 'T':'Temperature',
                      'DIC':'Dissolved Inorganic Carbon', 'ALK' : 'Alkalinity'}

        if filename:
            self._files = os.path.join(dirin, filename)
            self.logger.debug("Reading {}".format(self._files))
            self.ds = xr.open_dataset(self._files, decode_times=False)
            self.ds.rename({'depth': 'z_t'}, inplace=True)
        else:
            self.ds = xr.Dataset()
            for varname_generic, varname in self._var_dict.items():
                v = self._woa_names[varname_generic] # pylint: disable=invalid-name

                self._list_files(dirin=dirin, v=v, freq=freq, grid=grid)
                dsi = xr.open_mfdataset(self._files, decode_times=False)

                if '{}_an'.format(v) in dsi.variables and varname != '{}_an'.format(v):
                    dsi.rename({'{}_an'.format(v):varname}, inplace=True)

                dsi = dsi.drop([k for k in dsi.variables if '{}_'.format(v) in k])

                if self.ds.variables:
                    self.ds = xr.merge((self.ds, dsi))
                else:
                    self.ds = dsi

        # Unit conversion (ml/L -> mmol/m3); also shorten micromoles_per_liter
        for varname in self.ds:
            if 'units' in self.ds[varname].attrs:
                if self.ds[varname].attrs['units'] == 'ml l-1':
                    self.ds[varname].values = self.ds[varname].values * mlperl_2_mmolm3
                    self.ds[varname].attrs['units'] = 'mmol m$^{-3}$'

                if self.ds[varname].attrs['units'] == 'micromoles_per_liter':
                    self.ds[varname].attrs['units'] = 'mmol m$^{-3}$'
            if varname in long_names:
                self.ds[varname].attrs['long_name'] = long_names[varname]

        if freq == 'ann':
            self._is_ann_climo = True
            self._is_mon_climo = False
        elif freq == 'mon':
            self._is_ann_climo = False
            self._is_mon_climo = True
        else:
             raise ValueError("frequency must be 'ann' or 'mon'")

    def _list_files(self, dirin, v, freq='ann', grid='1x1d'):
        """ docstring """

        if grid == '1x1d':
            res_code = '01'
        elif grid == 'POP_gx1v7':
            res_code = 'gx1v7'

        files = []
        for code in woa_time_freq(freq):
            if v in ['t', 's']:
                files.append('woa13_decav_{}{}_{}v2.nc'.format(v, code, res_code))
            elif v in ['o', 'p', 'n', 'i', 'O', 'A']:
                files.append('woa13_all_{}{}_{}.nc'.format(v, code, res_code))
            else:
                raise ValueError('no file template defined for {}'.format(v))

        self._files = [os.path.join(dirin, grid, f) for f in files]

    def compute_mon_climatology(self):
        """ WOA2013 data should already be climatology """
        pass

######################################################################

def woa_time_freq(freq):
    """ docstring """
    # 13: jfm, 14: amp, 15: jas, 16: ond

    if freq == 'ann':
        time_freq = ['00']
    elif freq == 'mon':
        time_freq = ['%02d' % m for m in range(1, 13)]
    elif freq == 'jfm':
        time_freq = ['13']
    elif freq == 'amp':
        time_freq = ['14']
    elif freq == 'jas':
        time_freq = ['15']
    elif freq == 'ond':
        time_freq = ['16']
    return time_freq
