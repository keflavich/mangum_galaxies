"""

Derive Moment0, Moment1, and Moment2 from a reasonably-well separated spectral line in
an image cube.  Simply calculates moments over a defined HWZI for each line in band.

To run in ipython use:

run ~/Python/CubeLineMoment.py

"""
from __future__ import print_function

import numpy as np
from spectral_cube import SpectralCube
from astropy import units as u
import pyregion
import pylab as pl
import yaml

from astropy import log
log.setLevel('CRITICAL') # disable most logger messages



def cubelinemoment_setup(cube, cuberegion, spatialmaskcube,
                         spatialmaskcuberegion, vz, brightest_line_frequency,
                         width_line_frequency, linewidth_guess,
                         noisemapbright_baseline, noisemap_baseline,
                         spatial_mask_limit, **kwargs):
    """
    For a given cube file, read it and compute the moments (0,1,2) for a
    selection of spectral lines.  This code is highly configurable.

    In the parameter description, 'PPV' refers to position-position-velocity,
    and all cubes are expected to be in this space.  Velocity is
    generally interchangeable with frequency, but many operations must be
    performed in velocity space.

    Parameters
    ----------
    cube : str
        The cube file name
    cuberegion : str, optional
        A ds9 region file specifying a spatial region to extract from the cube
    spatialmaskcube : str
        Filename of a cube that specifies the PPV region over which the moments
        will be extracted.
    spatialmaskcuberegion : str, optional
        A ds9 region file specifying a spatial region to extract from the
        spatial mask cube.  Should generally be the same as cuberegion.
        NOTE TO JEFF: should this *always* be the same as cuberegion?
    vz : `astropy.units.Quantity` with km/s equivalence
        The line-of-sight velocity of the source, e.g., the redshift.
    target : str
        Name of the source.  Used when writing output files.
    brightest_line_frequency : `astropy.units.Quantity` with Hz equivalence
        The frequency of the brightest line, used to establish the cube volume
        over which to compute moments for other lines
    width_line_frequency : `astropy.units.Quantity` with Hz equivalence
        The central frequency of the line used to compute the width (moment 2)
    linewidth_guess : `astropy.units.Quantity` with km/s equivalence
        The approximate full-width zero-intensity of the lines.  This parameter
        is used to crop out regions of the cubes around line centers.  It
        should be larger than the expected FWHM line width.
    noisemapbright_baseline : list of lists
        A list of pairs of indices over which the noise can be computed from
        the 'bright' cube
        NOTE TO JEFF: It would probably be better to specify this in GHz or
        km/s.  That will require a slight change in the code, but will make
        it more robust to changes in, e.g., linewidth or other parameters
        that can affect the cube shape.
    noisemap_baseline : list of lists
        A list of pairs of indices over which the noise can be computed from
        the main cube
    spatial_mask_limit : float
        Factor in n-sigma above which to apply threshold to data.


    Returns
    -------
    A variety of cubes and maps
    """

    # Read the FITS cube
    # And change the units back to Hz
    cube = SpectralCube.read(cube).with_spectral_unit(u.Hz)

    # cut out a region that only includes the Galaxy (so we don't have to worry
    # about masking later)
    if cuberegion is not None:
        cube = cube.subcube_from_ds9region(pyregion.open(cuberegion))

    # --------------------------
    # Define a spatial mask that guides later calculations by defining where
    # dense gas is and is not.
    # For the NGC253 Band 6 data use the C18O 2-1 line in spw1 for the dense
    # gas mask for all Band 6 lines.
    #    spatialmaskcube = SpectralCube.read('NGC253-H213COJ32K1-Feather-line-All.fits').with_spectral_unit(u.Hz).subcube_from_ds9region(pyregion.open('ngc253boxband6tight.reg'))
    spatialmaskcube = SpectralCube.read(spatialmaskcube).with_spectral_unit(u.Hz).subcube_from_ds9region(pyregion.open(spatialmaskcuberegion))
    # For the NGC4945 Band 6 data use the C18O 2-1 line in spw1 for the dense
    # gas mask for all Band 6 lines.
    #spatialmaskcube = SpectralCube.read('NGC4945-H213COJ32K1-Feather-line.fits').with_spectral_unit(u.Hz).subcube_from_ds9region(pyregion.open('ngc4945boxband6.reg'))

    # redshift velocity
    #    vz = 258.8*u.km/u.s # For NGC253
    vz = u.Quantity(vz, u.km/u.s) # For NGC253
    #vz = 538.2*u.km/u.s # For NGC4945

    # Lines to be analyzed (including brightest_line)
    #    target = 'NGC253'
    #target = 'NGC4945'

    #    brightest_line_frequency = 219.560358*u.GHz # C18O 2-1
    brightest_line_frequency = u.Quantity(brightest_line_frequency, u.GHz) # C18O 2-1
    #    width_line = 218.222192*u.GHz # H2CO 3(03)-2(02)
    width_line_frequency = u.Quantity(width_line_frequency, u.GHz) # H2CO 3(03)-2(02)

    # Assume you have a constant expected width (HWZI) for the brightest line
    # Note: This HWZI should be larger than those assumed in the line extraction loop below...
    #    width = 80*u.km/u.s
    linewidth_guess = u.Quantity(linewidth_guess, u.km/u.s)

    # ADAM'S ADDITIONS HERE
    # Use the H2CO 303_202 line (H2COJ32K02) as a mask for line widths...
    vcube = cube.with_spectral_unit(u.km/u.s, rest_value=width_line_frequency,
                                    velocity_convention='optical')
    width_map = vcube.linewidth_sigma() # or vcube.moment2(axis=0)**0.5
    centroid_map = vcube.moment1(axis=0)
    max_map = cube.max(axis=0)
    #max_width = width_map.max() # should be ~150 km/s?
    #max_fwhm_width = max_width * (8*np.log(2))**0.5 # convert from sigma to FWHM

    # Create a copy of the SpatialMaskCube with velocity units
    spatialmask_Vcube = spatialmaskcube.with_spectral_unit(u.km/u.s,
                                                           rest_value=brightest_line_frequency,
                                                           velocity_convention='optical')

    # Use the brightest line to identify the appropriate peak velocities, but ONLY
    # from a slab including +/- width:
    brightest_cube = spatialmask_Vcube.spectral_slab(vz-linewidth_guess,
                                                     vz+linewidth_guess)

    peak_velocity = brightest_cube.spectral_axis[brightest_cube.argmax(axis=0)]
    #pl.figure(2).clf()
    #pl.imshow(peak_velocity.value)
    #pl.colorbar()

    # make a spatial mask excluding pixels with no signal
    # (you can do better than this - this is the trivial, first try algorithm)
    peak_amplitude = brightest_cube.max(axis=0)
    # found this range from inspection of a spectrum:
    # s = cube.max(axis=(1,2))
    # s.quicklook()
    #noisemap = cube.spectral_slab(362.603*u.GHz, 363.283*u.GHz).std(axis=0)
    # Channel selection matches that used for continuum subtraction
    #
    # From NGC253 H213COJ32K1 spectral baseline
    inds = np.arange(cube.shape[0])
    mask = np.zeros_like(inds, dtype='bool')
    for low,high in noisemapbright_baseline:
        mask[low:high] = True
    noisemapbright = cube.with_mask(mask[:,None,None]).std(axis=0)
    # From NGC4945 H213COJ32K1 spectral baseline
    #noisemapbright = spatialmaskcube[165:185,:,:].std(axis=0)
    print("noisemapbright peak = {0}".format(np.nanmax(noisemapbright)))

    # Make a plot of the noise map...
    pl.figure(2).clf()
    pl.imshow(noisemapbright.value)
    pl.colorbar()
    #
    # Use 3*noisemap for spatial masking
    spatial_mask = peak_amplitude > spatial_mask_limit*noisemapbright
    # --------------------------

    # Now process spw of interest...
    #
    # Now define noise map for spw being analyzed...
    # From NGC253 H2COJ32K02 spectral baseline
    #noisemap = cube[360:370,:,:].std(axis=0)
    # ADAM ADDED: Derive noisemap over non-contiguous baseline
    # JGM: Had to go back to defining noisemap_baseline in function as param input of list does not seem to work
    #noisemap_baseline = [(9, 14), (40, 42), (72, 74), (114, 122), (138, 143), (245, 254), (342, 364)]
    inds = np.arange(cube.shape[0])
    mask = np.zeros_like(inds, dtype='bool')
    for low,high in noisemap_baseline:
        mask[low:high] = True
    noisemap = cube.with_mask(mask[:,None,None]).std(axis=0)
    
    return (cube, spatialmaskcube, spatial_mask, noisemap, noisemapbright,
            centroid_map, width_map, max_map, peak_velocity)



def cubelinemoment_multiline(cube, peak_velocity, centroid_map, max_map, noisemap,
                             signal_mask_limit, spatial_mask_limit,
                             my_line_list, my_line_widths, my_line_names,
                             target, spatial_mask, width_map, **kwargs):
    """
    Given the appropriate setup, extract moment maps for each of the specified
    lines

    Parameters
    ----------
    peak_velocity : `astropy.units.Quantity` with km/s equivalence
    centroid_map : `astropy.units.Quantity` with km/s equivalence
    max_map : `astropy.units.Quantity` with brightness or flux unit
    noisemap : `astropy.units.Quantity` with brightness or flux unit
    my_line_list : `astropy.units.Quantity` with Hz equivalence
        An array of line centers to compute the moments of
    my_line_widths : `astropy.units.Quantity` with km/s equivalence
        An array of line widths matched to ``my_line_list``.
    my_line_names : list of strings
        A list of names matched to ``my_line_list`` and ``my_line_widths``.
        Used to specify the output filename.
    spatial_mask_limit : float
        Factor in n-sigma above which to apply threshold to data.
    signal_mask_limit : float
        Factor in n-sigma above which to apply threshold to data.

    Returns
    -------
    None.  Outputs are saved to files in the momentX/ subdirectory,
    where X is in {0,1,2}
    """

    # parameter checking
    if len(my_line_names) != len(my_line_list) or len(my_line_names) != len(my_line_widths):
        raise ValueError("Line lists (central frequency, names, and widths) "
                         "have different lengths")


    # Now loop over EACH line, extracting moments etc. from the appropriate region:
    # we'll also apply a transition-dependent width (my_line_widths) here because
    # these fainter lines do not have peaks as far out as the bright line.

    for line_name,line_freq,line_width in zip(my_line_names,my_line_list,my_line_widths):

        line_freq = u.Quantity(line_freq,u.GHz)
        line_width = u.Quantity(line_width,u.km/u.s)
        vcube = cube.with_spectral_unit(u.km/u.s, rest_value=line_freq,
                                        velocity_convention='optical')

        subcube = vcube.spectral_slab(peak_velocity.min()-line_width,
                                      peak_velocity.max()+line_width)

        # ADAM'S ADDITIONS AGAIN
        # use the spectral_axis to make a 'mask cube' with the moment1/moment2
        # values computed for the selected mask line (H2CO 303?)
        # We create a Gaussian along each line-of-sight, then we'll crop based on a
        # threshold
        # The [:,:,None] and [None,None,:] allow arrays of shape [x,y,0] and
        # [0,0,z] to be "broadcast" together
        assert centroid_map.unit.is_equivalent(u.km/u.s)
        gauss_mask_cube = np.exp(-(np.array(centroid_map)[None,:,:] -
                                   np.array(subcube.spectral_axis)[:,None,None])**2 /
                                 (2*np.array(width_map)[None,:,:]**2))
        peak_sn = max_map / noisemap

        print("Peak S/N: {0}".format(np.nanmax(peak_sn)))

        # threshold at the fraction of the Gaussian corresponding to our peak s/n.
        # i.e., if the S/N=6, then the threshold will be 6-sigma
        # (this can be modified as you see fit)
        threshold = np.exp(-(peak_sn**2) / 2.)
        print("Highest Threshold: {0}".format(np.nanmax(threshold)))
        print("Lowest Threshold: {0}".format((threshold[threshold>0].min())))

        # this will compare the gaussian cube to the threshold on a (spatial)
        # pixel-by-pixel basis
        width_mask_cube = gauss_mask_cube > threshold
        print("Number of values above threshold: {0}".format(width_mask_cube.sum()))
        print("Max value in the mask cube: {0}".format(np.nanmax(gauss_mask_cube)))
        print("shapes: mask cube={0}  threshold: {1}".format(gauss_mask_cube.shape, threshold.shape))



        # this part makes a cube of velocities
        temp = subcube.spectral_axis
        velocities = np.tile(temp[:,None,None], subcube.shape[1:])

        # now we use the velocities from the brightest line to create a mask region
        # in the same velocity range but with different rest frequencies (different
        # lines)
        mask = np.abs(peak_velocity - velocities) < line_width

        # Mask on a pixel-by-pixel basis with a 3-sigma cut
        signal_mask = subcube > signal_mask_limit*noisemap

        # the mask is a cube, the spatial mask is a 2d array, but in this case
        # numpy knows how to combine them properly
        # (signal_mask is a different type, so it can't be combined with the others
        # yet - I'll add a feature request for that)
        msubcube = subcube.with_mask(mask & spatial_mask).with_mask(signal_mask).with_mask(width_mask_cube)

        # Now write output.  Note that moment0, moment1, and moment2 directories
        # must already exist...
    
        labels = {0: 'Integrated Intensity [{0}]',
                  1: '$V_{{LSR}}$ [{0}]',
                  #2: '$\sigma_v$ [{0}]',
                  2: '$FWHM$ [{0}]',
                 }

        for moment in (0,1,2):
            mom = msubcube.moment(order=moment, axis=0)
            if moment == 2:
                mom = np.multiply(2*np.sqrt(np.log(2)),np.sqrt(mom))
            hdu = mom.hdu
            hdu.header.update(cube.beam.to_header_keywords())
            hdu.header['OBJECT'] = cube.header['OBJECT']
            hdu.writeto("moment{0}/{1}_{2}_moment{0}.fits".format(moment,target,line_name), clobber=True)
            pl.figure(1).clf()
            mom.quicklook() #filename='moment{0}/{1}_{2}_moment{0}.png'.format(moment,target,line_name))
            mom.FITSFigure.colorbar.show(axis_label_text=labels[moment].format(mom.unit.to_string('latex_inline')))
            mom.FITSFigure.save(filename='moment{0}/{1}_{2}_moment{0}.png'.format(moment,target,line_name))
            mom.FITSFigure.close()

def main():
    """
    To avoid ridiculous namespace clashes
    http://stackoverflow.com/questions/4775579/main-and-scoping-in-python
    """

    import argparse

    parser = argparse.ArgumentParser(description='Derive moment maps for a'
                                     ' cube given a complex suite of'
                                     ' parameters')
    parser.add_argument('param_file', metavar='pars', type=str,
                        help='The name of the YAML parameter file')

    args = parser.parse_args()
    
    infile = args.param_file

    # Read input file which sets all parameters for processing
    # Example call:
    # ipython:
    # %run CubeLineMoment.py yaml_scripts/NGC253-H2COJ32K02-CubeLineMomentInput.yaml
    # cmdline:
    # python CubeLineMoment.py yaml_scripts/NGC253-H2COJ32K02-CubeLineMomentInput.yaml

    with open(infile) as fh:
        params = yaml.load(fh)

    print(params)


    params['my_line_list'] = u.Quantity(list(map(float, params['my_line_list'].split(", "))), u.GHz)
    params['my_line_widths'] = u.Quantity(list(map(float, params['my_line_widths'].split(", "))), u.km/u.s)
    params['my_line_names'] = params['my_line_names'].split(", ")

    # Read parameters from dictionary

    (cube, spatialmaskcube, spatial_mask, noisemap, noisemapbright,
     centroid_map, width_map, max_map, peak_velocity) = cubelinemoment_setup(**params)

    params.pop('cube')

    cubelinemoment_multiline(cube=cube, spatial_mask=spatial_mask,
                             peak_velocity=peak_velocity,
                             centroid_map=centroid_map, max_map=max_map,
                             noisemap=noisemap, width_map=width_map, **params)


    if False:
        guesses = np.array([max_map.value, centroid_map.value, width_map.value])
        import pyspeckit
        vcube = cube.with_spectral_unit(u.km/u.s, velocity_convention='optical')
        pcube = pyspeckit.Cube(cube=vcube)
        pcube.mapplot.plane = max_map.value
        pcube.fiteach(guesses=guesses, start_from_point=(150,150),
                      errmap=noisemap.value)

if __name__ == "__main__":
    main()
