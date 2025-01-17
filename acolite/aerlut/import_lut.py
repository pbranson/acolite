## def import_lut
## imports LUT made with 6SV and converts to NetCDF
## written by Quinten Vanhellemont, RBINS for the PONDER project
## 2016-07-05
## modifications:   2020-07-14 (QV)
##                  2021-01-16 (QV) added support for bz2 compressed luts
##                  2021-02-24 (QV) removed obsolete code
##                  2021-02-25 (QV) changed position of lut files (removed lutid directory), added removal of unzipped file
##                  2021-03-02 (QV) integrated sensor specific LUTs
##                  2021-05-31 (QV) added remote lut retrieval
##                  2021-06-08 (QV) added lut par subsetting

def import_lut(lutid, lutdir,
               lut_par = ['utott', 'dtott', 'astot', 'ttot', 'romix'],
               override = False, sensor = None,
               get_remote = True, remote_base = 'https://raw.githubusercontent.com/acolite/acolite_luts/main'):

    import os, sys
    import numpy as np
    import acolite as ac

    lutnc=lutdir+'/'+lutid+'.nc'
    lut = None

    ## generic LUT
    if sensor is None:
        ## extract bz2 files
        unzipped = False
        lutncbz2 = '{}.bz2'.format(lutnc)
        if (not os.path.isfile(lutnc)) & (os.path.isfile(lutncbz2)):
            import bz2, shutil
            with bz2.BZ2File(lutncbz2) as fi, open(lutnc,"wb") as fo:
                shutil.copyfileobj(fi,fo)
            unzipped = True
        ## end extract bz2 files

        ## read dataset from NetCDF
        try:
            if os.path.isfile(lutnc):
                from netCDF4 import Dataset
                nc = Dataset(lutnc)
                meta=dict()
                for attr in nc.ncattrs():
                    attdata = getattr(nc,attr)
                    if isinstance(attdata,str): attdata = attdata.split(',')
                    meta[attr]=attdata
                lut = nc.variables['lut'][:]
                nc.close()
        except:
            print(sys.exc_info()[0])
            print('Failed to open LUT data from NetCDF (id='+lutid+')')

        if unzipped: os.remove(lutnc) ## clear unzipped LUT

        if lut is None:
            print('Could not import LUT {} from {}'.format(lutid, lutdir))
            return()

        ## subset LUTs
        if lut_par is not None:
            lut_sub_idx = []
            lut_sub_par = []
            for i, ik in enumerate(lut_par):
                for j, jk in enumerate(meta['par']):
                    if (ik == jk):
                        lut_sub_idx.append(j)
                        lut_sub_par.append(jk)
            meta['par'] = lut_sub_par
            lut = lut[lut_sub_idx,:,:,:,:,:,:]

        ## for the  and Continental and Urban models (1,3)
        ## romix nans were retrieved for wavelengths > 2 micron and aot == 0.001
        ## 500mb for C+U and 1013/1100 for U
        ## if any nans set then to 0
        sub = np.where(np.isnan(lut))
        lut[sub] = 0
        return(lut, meta)

    ## sensor specific LUT
    else:
        ## sensor LUT NetCDF is stored here
        lutnc_s='{}/{}/{}_{}.nc'.format(lutdir,sensor,lutid,sensor)
        if not os.path.exists(os.path.dirname(lutnc_s)): os.makedirs(os.path.dirname(lutnc_s))
        if (os.path.isfile(lutnc_s)) & (override): os.remove(lutnc_s)

        if (not os.path.isfile(lutnc_s)) | (override):
            ## try downloading LUT from GitHub
            if (get_remote):
                slut = '{}_{}'.format(lutid, sensor)
                remote_lut = '{}/{}/{}/{}.nc'.format(remote_base, '-'.join(lutid.split('-')[0:3]), sensor, slut)
                try:
                    ac.shared.download_file(remote_lut, lutnc_s)
                except:
                    print('Could not download remote lut {} to {}'.format(remote_lut, lutnc_s))

            ## otherwise to local resampling
            if (not os.path.isfile(lutnc_s)):
                print('Resampling LUT {} to sensor {}'.format(lutid, sensor))
                rsrd = ac.shared.rsr_dict(sensor=sensor)
                rsr, rsr_bands = rsrd[sensor]['rsr'], rsrd[sensor]['rsr_bands']

                ## read LUT
                lut, meta = ac.aerlut.import_lut(lutid,lutdir)
                lut_dims = lut.shape

                ## new ndim convolution
                lut_sensor = {}
                for band in rsr_bands:
                    lut_sensor[band] = ac.shared.rsr_convolute_nd(lut, meta['wave'],rsr[band]['response'], rsr[band]['wave'], axis=1)

                ## write nc file
                try:
                    if os.path.isfile(lutnc_s) is False:
                        from netCDF4 import Dataset
                        nc = Dataset(lutnc_s, 'w', format='NETCDF4_CLASSIC')
                        ## write metadata
                        for i in meta:
                            attdata=meta[i]
                            if isinstance(attdata,list):
                                if isinstance(attdata[0],str):
                                    attdata=','.join(attdata)
                            setattr(nc, i, attdata)
                        ## set up LUT dimension
                        nc.createDimension('par', lut_dims[0])
                        #nc.createDimension('wave', lut_dims[1]) # not used here
                        nc.createDimension('azi', lut_dims[2])
                        nc.createDimension('thv', lut_dims[3])
                        nc.createDimension('ths', lut_dims[4])
                        nc.createDimension('wnd', lut_dims[5])
                        nc.createDimension('tau', lut_dims[6])
                        ## write LUT
                        for band in lut_sensor.keys():
                            var = nc.createVariable(band,np.float32,('par','azi','thv','ths','wnd','tau'))
                            nc.variables[band][:] = lut_sensor[band].astype(np.float32)
                        nc.close()
                        nc = None
                        arr = None
                        meta = None
                except:
                    if os.path.isfile(lutnc_s): os.remove(lutnc_s)
                    print(sys.exc_info()[0])
                    print('Failed to write LUT data to NetCDF (id='+lutid+')')

        ## read dataset from NetCDF
        if os.path.isfile(lutnc_s):
            try:
                from netCDF4 import Dataset
                nc = Dataset(lutnc_s)
                ## read in metadata
                meta=dict()
                for attr in nc.ncattrs():
                    attdata = getattr(nc,attr)
                    if isinstance(attdata,str): attdata = attdata.split(',')
                    meta[attr]=attdata
                ## read in LUT
                lut_sensor = dict()
                datasets = list(nc.variables.keys())
                for dataset in datasets:
                    lut_sensor[dataset] = nc.variables[dataset][:]
                nc.close()
                nc = None
            except:
                print(sys.exc_info()[0])
                print('Failed to open LUT data from NetCDF (id='+lutid+')')

        ## subset LUTs
        if lut_par is not None:
            lut_sub_idx = []
            lut_sub_par = []
            for i, ik in enumerate(lut_par):
                for j, jk in enumerate(meta['par']):
                    if (ik == jk):
                        lut_sub_idx.append(j)
                        lut_sub_par.append(jk)
            meta['par'] = lut_sub_par
            for dataset in lut_sensor:
                lut_sensor[dataset] = lut_sensor[dataset][lut_sub_idx,:,:,:,:,:]

        return(lut_sensor, meta)
