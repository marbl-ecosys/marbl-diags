"""
Functions that can be called from analysis elements"""

import os
from subprocess import call
import cartopy
import cartopy.crs as ccrs
import numpy as np
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import plottools as pt

def plot_climo(AnalysisElement, config_dict):
    """ Regardless of data source, generate png """
    # look up grid (move to known grids database)
    if AnalysisElement._config_dict['grid'] == 'POP_gx1v7':
        # and is tracer....
        depth_coord_name = 'z_t'
    else:
        raise ValueError('unknown grid')

    # set up time dimension for averaging
    time_dims = dict()
    time_dims['ANN'] = range(0,12)
    time_dims['DJF'] = [11, 0, 1]
    time_dims['MAM'] = range(2,5)
    time_dims['JJA'] = range(5,8)
    time_dims['SON'] = range(8,11)

    # where will plots be written?
    dirout = AnalysisElement._config_dict['dirout']+'/plots'
    if not os.path.exists(dirout):
        call(['mkdir', '-p', dirout])

    # identify reference (if any provided)
    ref_data_source_name = None
    if AnalysisElement.reference:
        for data_source_name in AnalysisElement.data_sources:
            if AnalysisElement.reference == data_source_name:
                ref_data_source_name = data_source_name
    if ref_data_source_name:
        AnalysisElement.logger.info("Reference dataset: '%s'", ref_data_source_name)
    else:
        AnalysisElement.logger.info("No reference dataset specified")

    #-- loop over datasets
    data_source_name_list = AnalysisElement.data_sources.keys()
    if ref_data_source_name:
        data_source_name_list = [ref_data_source_name] + \
                                [data_source_name for data_source_name in data_source_name_list
                                    if data_source_name != ref_data_source_name]

    #-- loop over variables
    for v in AnalysisElement._config_dict['variable_list']:

        nrow, ncol = pt.get_plot_dims(len(data_source_name_list))
        AnalysisElement.logger.info('dimensioning plot canvas: %d x %d (%d total plots)',
                         nrow, ncol, len(data_source_name_list))

        #-- loop over time periods
        for time_period in config_dict['climo_time_periods']:

            for sel_z in AnalysisElement._config_dict['depth_list']:

                #-- build indexer for depth
                if isinstance(sel_z, list): # fragile?
                    is_depth_range = True
                    indexer = {depth_coord_name:slice(sel_z[0], sel_z[1])}
                    depth_str = '{:.0f}-{:.0f}m'.format(sel_z[0], sel_z[1])
                else:
                    is_depth_range = False
                    indexer = {depth_coord_name: sel_z, 'method': 'nearest'}
                    depth_str = '{:.0f}m'.format(sel_z)

                #-- name of the plot
                plot_name = '{}/state-map-{}.{}.{}.{}.png'.format(dirout,
                                                                  AnalysisElement._config_dict['short_name'],
                                                                  v,
                                                                  depth_str,
                                                                  time_period)
                AnalysisElement.logger.info('generating plot: %s', plot_name)

                #-- generate figure object
                fig = plt.figure(figsize=(ncol*6,nrow*4))

                for i, ds_name in enumerate(data_source_name_list):

                    ds = AnalysisElement.data_sources[ds_name].ds
                    #-- need to deal with time dimension here....

                    # Find appropriate variable name in dataset
                    var_name = AnalysisElement.data_sources[ds_name]._var_dict[v]
                    if var_name not in ds:
                        raise KeyError('Can not find {} in {}'.format(var_name, ds_name))
                    if time_period in time_dims:
                        field = ds[var_name].sel(**indexer).isel(time=time_dims[time_period]).mean('time')
                    else:
                        raise KeyError("'%s' is not a known time period" % time_period)
                    AnalysisElement.logger.info('Plotting %s from %s', var_name, ds_name)

                    if is_depth_range:
                        field = field.mean(depth_coord_name)

                    ax = fig.add_subplot(nrow, ncol, i+1, projection=ccrs.Robinson(central_longitude=305.0))

                    if AnalysisElement._config_dict['grid'] == 'POP_gx1v7':
                        lon, lat, field = pt.adjust_pop_grid(ds.TLONG.values, ds.TLAT.values, field)

                    if v not in AnalysisElement._var_dict:
                        raise KeyError('{} not defined in variable YAML dict'.format(v))

                    cf = ax.contourf(lon,lat,field,transform=ccrs.PlateCarree(),
                                     levels=AnalysisElement._var_dict[v]['contours']['levels'],
                                     extend=AnalysisElement._var_dict[v]['contours']['extend'],
                                     cmap=AnalysisElement._var_dict[v]['contours']['cmap'],
                                     norm=pt.MidPointNorm(midpoint=AnalysisElement._var_dict[v]['contours']['midpoint']))
                    del(field)
                    land = ax.add_feature(cartopy.feature.NaturalEarthFeature(
                        'physical','land','110m',
                        edgecolor='face',
                        facecolor='gray'))

                    ax.set_title(ds_name)
                    ax.set_xlabel('')
                    ax.set_ylabel('')

                fig.subplots_adjust(hspace=0.45, wspace=0.02, right=0.9)
                cax = plt.axes((0.93, 0.15, 0.02, 0.7))
                fig.colorbar(cf, cax=cax)

                fig.savefig(plot_name, bbox_inches='tight', dpi=300)
                plt.close(fig)