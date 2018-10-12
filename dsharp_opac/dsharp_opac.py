#!/usr/bin/env python
"""
This module contains opacity scripts and all the helper and testing routines.

- dielectric functions are objects, see bhmie.diel_*
  the functions `diel_*.nk` return the optical properties
"""
from __future__ import print_function
import numpy as np
import os
import sys
import warnings
import pkg_resources

# next we need to define the bhmie function. By default we try to use the
# fortran version which should be the fastest. Otherwise, we use a python
# version. If numba is installed, it will be used. To check what your
# installation uses, print out bhmie_type, which will be in decending speed
# fortran, numba, python. Another python implementation can also be used
# which is available via the wrapper bhmie_pymiecoated. To force the code to
# use another version than the (faster) one used by default is by calling
# the methods with the keyword
# `bhmie_function = `
# - `bhmie_fortran`
# - `bhmie_python_wrapper`
# - `bhmie_pymiecoated`

try:
    from .bhmie_fortran import bhmie_fortran
    bhmie_function = bhmie_fortran
    bhmie_type = 'fortran'

except ImportError:
    warnings.warn('could not import compiled mie code - mie calculation will be slow')
    from .bhmie_python import bhmie_python_wrapper
    from .bhmie_python import bhmie_type as bt
    bhmie_type = bt
    bhmie_function = bhmie_python_wrapper

try:
    import pymiecoated

    def bhmie_pymiecoated(x, nk, n_angles):
        """
        Wrapper to the Mie code of `pymiecoated`

        x : float
            size parameter x = 2 pi a / lambda

        nk : complex
            complex ref. index = n + i * k, e.g. `complex(1.,0.)`

        nangles : int
            number of angles between 0 and 90 degree. Will return S1 & S2 at
            2 * nangles - 1 angles between 0 and 180 degree.

        Output:
        -------
        S1, S2, Qext, Qabs, Qsca, Qback, gsca

        S1, S2 : arrays
            the matrix elements as function of angle

        Qext, Qabs, Qsca, Qback : float
            the extinction, absorption, scattering, backscattering coefficients

        gsca : float
            Henyey-Greenstein asymmetry factor
        """
        #
        # the other code
        #
        opac = pymiecoated.Mie(x=x, m=nk)
        Qext = opac.qext()
        Qabs = opac.qabs()
        Qsca = opac.qsca()
        Qback = opac.qratio()
        gsca = opac.asy()

        S1 = np.zeros(2 * n_angles - 1, dtype=complex)
        S2 = np.zeros(2 * n_angles - 1, dtype=complex)

        angles = np.linspace(0., 180., 2 * n_angles - 1)

        for i, angle in enumerate(angles):
            S1[i], S2[i] = opac.S12(np.cos(angle / 180 * np.pi))

        return S1, S2, Qext, Qabs, Qsca, Qback, gsca
except ImportError:
    pass


def progress_bar(perc, text=''):
    """
    Displays a progress bar.

    This is a very simple progress bar which displays the given
    percentage of completion on the command line, overwriting its
    previous output.

    Arguments:
    perc    The percentage of completion (float), should be
             between 0 and 100. Only 100.0 finishes with the
             word "Done!".
    text    Possible text for describing the running process.

    Example:
    >>> import time
    >>> for i in linspace(0,100,1000):
    >>>     progress_bar(i,text='Waiting')
    >>>     time.sleep(0.005)
    """
    if text != '':
        text = text + ' ... '
    if perc == 100.0:
        sys.stdout.write('\r' + text + 'Done!\n')
        sys.stdout.flush()
    else:
        sys.stdout.write('\r' + text + '%d %%' % round(perc))
        sys.stdout.flush()


def download(packagedir):
    """
    Downloads the optical constants files. It works by getting the data from
    a json file `links.json` in `packagedir`.
    """
    import json
    import os
    from urllib.request import urlretrieve

    if not os.path.isdir(packagedir):
        packagedir = os.path.dirname(packagedir)

    with open(os.path.join(packagedir, 'links.json')) as f:
        data = json.load(f)
        for material, link in data.items():

            filename = link.split('/')[-1]

            print('material: {}, downloading {}: ... '.format(material, filename), end='')
            try:
                urlretrieve(link, filename=os.path.join(packagedir, filename))
                print('Done!')
            except Exception as ex:
                print('Failed!')
                raise ex


class diel_const(object):
    """
    Abstract class for dielectric constants objects
    """
    #
    # define the attributes of the class
    #
    datafile = ""
    _l = None
    _n = None
    _k = None
    _ll = None
    _ln = None
    _lk = None
    headerinfo = None
    material_str = None
    _lmin = None
    _lmax = None
    extrapol = False
    _has_negative_n = False
    rho = None

    def __init__(self, lam, n, k):
        """
        Initialization of data and such
        """
        if np.isscalar(lam):
            h = 1e-10 * lam
            lam = np.array([lam - h, lam + h])
            n = np.ones_like(lam) * n
            k = np.ones_like(lam) * k

        self._l = lam
        self._n = n
        self._k = k
        self._ll = np.log10(lam)
        self._ln = np.log10(n)
        self._lk = np.log10(k)
        self._lmin = lam[0]
        self._lmax = lam[-1]
        self._has_negative_n = np.any(n <= 0)

    def nk(self, l):
        """
        Return the optical properties interpolated at wavelength l

        Arguments:
        ----------

        l : float or array
        :    wavelength in cm

        Output:
        -------
        n : float
        :    real part of optical property

        k : float
        :    imaginary part of optical property
        """
        if np.array(l, ndmin=1).min() < self._lmin or np.array(l, ndmin=1).max() > self._lmax:
            raise NameError('{}: wavelength {:g} outside data-range [{:g},{:g}]'.format(type(self).__name__, l, self._lmin, self._lmax))

        log_interp = True
        if self._has_negative_n:
            # estimate if log interpolation is ok to do
            n = np.interp(l, self._l, self._n)
            if n < 0:
                log_interp = False

        if log_interp:
            result = 10.**np.interp(np.log10(l), self._ll, self._ln), 10.**np.interp(np.log10(l), self._ll, self._lk)
        else:
            result = np.interp(l, self._l, self._n), 10.**np.interp(np.log10(l), self._ll, self._lk)

        return result

    def extrapolate_constants_up(self, lmin, lmax, n=10, kind='second'):
        """
        Extend the data by log-extrapolation to longer wavelengths. Will start
        fitting for extrapolation at lmin and then extend the data up to lmax.
        """
        #
        # extrapolate
        #
        self.extrapol = True
        if self._has_negative_n:
            warnings.warn('Extrapolation for negative n values can cause issues')

        l_ext = np.logspace(np.log10(self._l[-1]), np.log10(lmax), n)[1:]
        from scipy.optimize import curve_fit

        if kind == 'constant':
            n_ext = self._n[-1] * np.ones_like(l_ext)
            k_ext = self._k[-1] * np.ones_like(l_ext)

        elif kind == 'second':
            def f(x, a, b, c):
                return a + b * x + c * x**2

            # starting points

            p0_n = [np.log10(self._n[-1]), 1, 0]
            p0_k = [np.log10(self._k[-1]), 1, 0]

        elif kind in ['first', 'linear']:
            def f(x, a, b):
                return a + b * x

            # starting points
            p0_n = [np.log10(self._n[-1]), 1]
            p0_k = [np.log10(self._k[-1]), 1]

        else:
            raise ValueError('`kind` must be `first` or `second`')

        if kind != 'constant':
            i_min = abs(self._l - lmin).argmin()
            #
            # extrapolate n
            #
            res = curve_fit(f, np.log10(self._l[i_min:]), np.log10(self._n[i_min:]), p0_n)
            n_ext = 10.**f(np.log10(l_ext), *res[0])
            #
            # extrapolate k
            #
            res = curve_fit(f, np.log10(self._l[i_min:]), np.log10(self._k[i_min:]), p0_k)
            k_ext = 10.**f(np.log10(l_ext), *res[0])

        # update attributes

        self._l = np.append(self._l, l_ext)
        self._n = np.append(self._n, n_ext)
        self._k = np.append(self._k, k_ext)
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.material_str += ' - extrapolated'

    def extrapolate_constants_down(self, lmin, lmax, n=10, kind='second'):
        """
        Extend the data by log-extrapolation to shorter wavelengths. Will start
        fitting for extrapolation at lmax and then extend the data down to lmin.
        """
        #
        # extrapolate
        #
        self.extrapol = True
        if self._has_negative_n:
            warnings.warn('Extrapolation for negative n values can cause issues')

        l_ext = np.logspace(np.log10(lmin), np.log10(self._l[0]), n)[:-1]
        from scipy.optimize import curve_fit

        if kind == 'constant':
            n_ext = self._n[0] * np.ones_like(l_ext)
            k_ext = self._k[0] * np.ones_like(l_ext)

        elif kind == 'second':
            def f(x, a, b, c):
                return a + b * x + c * x**2

            # starting points

            p0_n = [np.log10(self._n[0]), 0, 0]
            p0_k = [np.log10(self._k[0]), 0, 0]

        elif kind in ['first', 'linear']:
            def f(x, a, b):
                return a + b * x

            # starting points
            p0_n = [np.log10(self._n[0]), 1]
            p0_k = [np.log10(self._k[0]), 1]

        else:
            raise ValueError('`kind` must be `first` or `second`')

        if kind != 'constant':
            i_max = abs(self._l - lmax).argmin()
            #
            # extrapolate n
            #
            res = curve_fit(f, np.log10(self._l[:i_max]), np.log10(self._n[:i_max]), p0_n)
            n_ext = 10.**f(np.log10(l_ext), *res[0])
            #
            # extrapolate k
            #
            res = curve_fit(f, np.log10(self._l[:i_max]), np.log10(self._k[:i_max]), p0_k)
            k_ext = 10.**f(np.log10(l_ext), *res[0])

        # update attributes

        self._l = np.append(l_ext, self._l)
        self._n = np.append(n_ext, self._n)
        self._k = np.append(k_ext, self._k)
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.material_str += ' - extrapolated'


class diel_from_lnk_file(diel_const):
    """
    returns the dielectric constants from a given lnk file.
    The lnk data needs to be in 3 columns:
    lambda [microns], n, k

    Arguments:
    ----------
    datafile : str
    :    path of lnk-file

    Keywords:
    ---------
    headerlines : int
    :    number of lines in header
    """

    def __init__(self, datafile, headerlines=0):
        """
        Overwrite the initialization of the parent class
        """
        #
        # open file, read header and data
        #
        self.datafile = datafile
        self.material_str = 'Optical constants from %s' % datafile
        f = open(self.datafile)
        self.headerinfo = [f.readline() for i in range(headerlines)]
        data = np.loadtxt(f)
        #
        # assign wavelength and optical constants
        #
        self._l = data[:, 0] * 1e-4
        self._n = data[:, 1]
        self._k = data[:, 2]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()

        if any(self._n <= 0):
            self._has_negative_n = True


class diel_henning(diel_const):
    """
    Returns the dielectric constants for the various optical constants
    from Thomas Hennings website.

    Arguments:
    ----------

    species : str
    :    name of the species to read. Possible choices are
         iron,olivine,organics,orthopyroxene,troilite,waterice


    Keywords:
    ---------

    type : str
    :    only for olivine and orthopyroxene decide between
         'low'    = low iron abundance
         'normal' = normal iron abundance
         'high'   = high iron abundance

    new : bool
    :    use the old version of the constants, for this case,
         only normal iron abundance is avaliable

    """

    def __init__(self, species, refractory=False, iron_abundance='normal', new=True):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        self.material_str = species[0].upper() + species[1:] + ' (Henning)'

        if iron_abundance not in ['normal', 'low', 'high']:
            raise NameError('unknown iron abundance')
        if species not in ['iron', 'olivine', 'organics', 'orthopyroxene', 'troilite', 'waterice']:
            raise NameError('unknown abundance species')
        if (iron_abundance != 'normal') and ((not new) or (species not in ['olivine', 'orthopyroxene'])):
            raise NameError('low & high iron only available for new olivine and new orthopyroxene')
        #
        # set the file name
        #
        if species in ['iron', 'organics', 'troilite', 'waterice']:
            fname = species + new * 'k'
        elif species == 'olivine':
            if iron_abundance == 'normal':
                fname = new * 'olmg70k' + (not new) * 'olivine'
            elif iron_abundance == 'low':
                fname = 'olivinenewk'
            elif iron_abundance == 'high':
                fname = 'olmg60k'
        elif species == 'orthopyroxene':
            if iron_abundance == 'normal':
                fname = new * 'pyrmg70k' + (not new) * 'orthopyr'
            elif iron_abundance == 'low':
                fname = 'pyrmg100k'
            elif iron_abundance == 'high':
                fname = 'pyrmg60k'

        densities = {
            'olmg70k': 3.49,
            'olivine': 3.49,
            'olivinenewk': 3.20,
            'olmg60k': 3.59,
            'orthopyr': 3.40,
            'pyrmg100k': 3.20,
            'pyrmg60k': 3.42,
            'orthopyr': 3.40,
            'pyrmg70k': 3.40,
            'ironk': 7.87,
            'iron': 7.87,
            'organicsk': 1.5 * refractory + 1.0 * (not refractory),
            'organics': 1.5 * refractory + 1.0 * (not refractory),
            'troilitek': 4.83,
            'troilite': 4.83,
            'watericek': 0.92,
            'waterice': 0.92
            }
        self.rho = densities[fname]
        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'henning', 'new' * new + 'old' * (not new), fname + '.lnk'))
        if not os.path.isfile(self.datafile):
            self.download()
        #
        # read data
        #
        print('Reading opacities from %s' % fname)
        data = np.loadtxt(self.datafile)
        #
        # assign wavelength and optical constants
        #
        self._l = data[:, 0] * 1e-4
        self._n = data[:, 1]
        self._k = data[:, 2]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()

    def download(self):
        for i in ['old', 'new']:
            path = pkg_resources.resource_filename(__name__, os.path.join('optical_constants', 'henning', i))
            download(path)


class diel_jaeger98(diel_const):
    """
    Returns the dielectric constants for the various carbonaceous dust optical
    constants from:

    [Jaeger et al. 1998](http://adsabs.harvard.edu/abs/1998A%26A...332..291J)

    Densities are given as:

    | T [degree C] | 400   | 600   | 800   | 1000  |
    |:-------------|:------|:------|:------|:------|
    | rho [g/cm^3] | 1.435 | 1.670 | 1.843 | 1.988 |

    Arguments:
    ----------

    T : str
        temperature in celsius, can be [400, 600, 800, 1000]
    """

    def __init__(self, T):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        temps = [400, 600, 800, 1000]
        rhos  = [1.435, 1.670, 1.843, 1.988]
        assert T in temps, "invalid temperature, use {}".format(temps)
        self.material_str = 'Carbonaceous dust, T={} C (Jaeger et al. 1998)'.format(T)
        self.rho = rhos[temps.index(T)]

        fname = 'cel{}.lnk'.format(T)
        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'jaeger', fname))
        if not os.path.isfile(self.datafile):
            download(os.path.dirname(self.datafile))
        #
        # read data
        #
        print('Reading opacities from %s' % fname)
        data = np.loadtxt(self.datafile)
        #
        # assign wavelength and optical constants
        #
        self._l = data[::-1, 0] * 1e-4
        self._n = data[::-1, 1]
        self._k = data[::-1, 2]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()


class diel_preibisch93(diel_const):
    """
    Returns the dielectric constants for the materials discussed in

    [Preibisch et al. 1993](http://adsabs.harvard.edu/abs/1993A%26A...279..577P)

    And available from

        https://hera.ph1.uni-koeln.de/~ossk/Jena/tables/acneu.lnk
        https://hera.ph1.uni-koeln.de/~ossk/Jena/tables/diiceneu.lnk

    Arguments:
    ----------

    species : str
        which species to use, can be 'dirty ice', 'amorphous carbon'
    """

    def __init__(self, species):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        species = species.lower()
        options = ['dirty ice', 'amorphous carbon']
        assert species in options, "unknown species, use one of {}".format(options)
        self.material_str = '{}, (Preibisch et al. 1993)'.format(species.capitalize())

        if species == 'dirty ice':
            fname = 'diiceneu.lnk'
        elif species == 'amorphous carbon':
            fname = 'acneu.lnk'

        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'preibisch', fname))
        if not os.path.isfile(self.datafile):
            download(os.path.dirname(self.datafile))
        #
        # read data
        #
        print('Reading opacities from %s' % fname)
        data = np.loadtxt(self.datafile)
        #
        # assign wavelength and optical constants
        #
        self._l = data[:, 0]
        self._n = data[:, 1]
        self._k = data[:, 2]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()


class diel_pollack1994(diel_const):
    """
    Returns the DIGITIZED dielectric constants for the materials from
    Pollack et al. 1994

    [Pollack et al. 1994](https://dx.doi.org/10.1086/173677)

    These have been digitized from Fig. 1 in the paper and no guarantee can be
    given. There will be measurement errors from the digitization process.

    Arguments:
    ----------

    species : str
        which species to use, can be
            - water ice
            - troilite
            - organics
            - olivine
            - iron
            - orthopyroxene
    """

    def __init__(self, species):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        species = species.lower()
        options = ['water ice', 'troilite', 'organics', 'olivine', 'iron', 'orthopyroxene']
        assert species in options, "unknown species, use one of {}".format(options)
        self.material_str = '{}, (Pollack et al. 1994)'.format(species.capitalize())

        fname = 'P94-{}.lnk'.format(species.replace(' ', ''))

        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'pollack1994', fname))
        #
        # read data
        #
        print('Reading opacities from %s' % fname)
        data = np.loadtxt(self.datafile)
        #
        # assign wavelength and optical constants
        #
        self._l = data[:, 0]
        self._n = data[:, 1]
        self._k = data[:, 2]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()


class diel_draine2003(diel_const):
    """
    Returns the dielectric constants from [Draine 2003](https://dx.doi.org/10.1086/379123) for:

    - astronomical silicates (rho = 3.3 g/cc) from

        ftp://ftp.astro.princeton.edu/draine/dust/diel/callindex.out_silD03

    - graphite (rho=2.26 g/cc) from

        ftp://ftp.astro.princeton.edu/draine/dust/diel/callindex.out_CpaD03_0.01
        ftp://ftp.astro.princeton.edu/draine/dust/diel/callindex.out_CpaD03_0.10
        ftp://ftp.astro.princeton.edu/draine/dust/diel/callindex.out_CpeD03_0.01
        ftp://ftp.astro.princeton.edu/draine/dust/diel/callindex.out_CpeD03_0.10

    Arguments:
    ----------

    species : str
        which species to use, either 'astrosilicates' or 'graphite'

    The graphite species **needs** following keyword arguments

    parallel : bool
        alignment with E-field, either parallel (true) else perpendicular

    a : str
        either '0.01' (0.01 micron) or '0.10' (0.10 micron)

    """

    def __init__(self, species, **kwargs):
        """
        Overwrite the initialization of the parent class
        """
        options = ['astrosilicates', 'graphite']
        assert species.lower() in options, 'unknown species, use one of {}'.format(options)
        #
        # open file, read header and data
        #
        if species.lower() == 'astrosilicates':
            self.material_str = 'Astronomical Silicates (Draine 2003)'
            fname = 'callindex.out_silD03'
            self.rho = 3.3  # laor & draine 93

        elif species.lower() == 'graphite':
            assert 'parallel' in kwargs, 'bool keyword \'parallel\' needed for graphite grains'
            assert 'a' in kwargs, 'str keyword \'a\' needed for graphite grains'
            parallel = kwargs.pop('parallel')
            a = kwargs.pop('a')
            self.material_str = 'Graphite, {}, a={} mu (Laor & Draine 1993)'.format(parallel * 'pa' + (not parallel) * 'pe', a)
            fname = 'callindex.out_C{}D03_{}'.format('pa' * parallel + 'pe' * (not parallel), a)
            self.rho = 2.26  # laor & draine 93

        # download file if needed

        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'draine', fname))
        if not os.path.isfile(self.datafile):
            download(os.path.dirname(self.datafile))

        # read from file

        with open(self.datafile) as f:
            self.headerinfo = [f.readline() for i in range(5)]
            data = np.loadtxt(f)
        #
        # assign wavelength and optical constants
        #
        self._l = data[-1::-1, 0] * 1e-4
        self._n = data[-1::-1, 3] + 1.
        self._k = data[-1::-1, 4]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()


class diel_WD2001_astrosil(diel_const):
    """
    Returns the dielectric constants for astronomical silicates from
    Weingartner & Draine 2001. The data comes from file `eps_suvSil`
    which was downloaded from

        ftp://ftp.astro.princeton.edu/draine/dust/diel/eps_suvSil

    on 2018-06-18--11:20 EDT
    """

    def __init__(self):
        """
        Overwrite the initialization of the parent class
        """
        #
        # open file, read header and data
        #
        self.material_str = 'Astronomical Silicates (Weingartner & Draine 2001)'
        self.datafile = pkg_resources.resource_filename(__name__, os.path.join(
            'optical_constants', 'draine', 'eps_suvSil'))
        if not os.path.isfile(self.datafile):
            download(os.path.dirname(self.datafile))
        f = open(self.datafile)
        self.headerinfo = [f.readline() for i in range(9)]
        data = np.loadtxt(f)
        #
        # assign wavelength and optical constants
        #
        self._l = data[-1::-1, 0] * 1e-4
        self._n = data[-1::-1, 3] + 1.
        self._k = data[-1::-1, 4]
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.rho = 3.5  # see sect 2.4


class diel_drainelee84_astrosil(diel_const):
    """
    Returns the dielectric constants for astronomical silicates from
    Draine & Lee 1984 (and Laor & Draine 1993). The data comes from eps_Sil
    which was downloaded from

        ftp://ftp.astro.princeton.edu/draine/dust/diel/eps_Sil

    on 2018-06-18--11:35 EDT
    """

    def __init__(self):
        """
        Overwrite the initialization of the parent class
        """
        #
        # open file, read header and data
        #
        self.material_str = 'Astronomical Silicates (Draine & Lee 1984)'
        self.datafile = pkg_resources.resource_filename(
            __name__, os.path.join('optical_constants', 'draine', 'eps_Sil'))
        if not os.path.isfile(self.datafile):
            download(os.path.dirname(self.datafile))
        with open(self.datafile) as f:
            self.headerinfo = [f.readline() for i in range(6)]
            data = np.loadtxt(f)
        #
        # assign wavelength and optical constants
        #
        self._l = data[::-1, 0] * 1e-4
        self._n = data[::-1, 3] + 1.
        self._k = data[::-1, 4]
        if any(self._n <= 0):
            self._has_negative_n = True
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.rho = 3.3  # DL84, page 102, 3rd paragraph


class diel_vacuum(diel_const):
    """
    Returns the dielectric constants for vacuum
    """
    extrapol = False
    _lmin = 0
    _lmax = 1e100
    _l = np.array(_lmin)
    _n = np.array([1.0])
    _k = np.array([0.0])
    _has_negative_n = True
    extrapol = False

    def __init__(self):
        """
        Overwrite the initialization of the parent class
        """
        self.material_str = 'Vacuum'

    def nk(self, l):
        """
        Get the n and k values at the given wavelength.
        """
        l = np.array(l, ndmin=1) # noqa
        return np.array([np.ones(len(l)), np.zeros(len(l))])


class diel_zubko96(diel_const):
    """
    Returns the dielectric constants for carbon grains from Zubko et
    al. 1996 [1] (the BE, ACH2 values). The data was OCRed by Til Birnstiel, no
    guarantee for correctness.

    Reference: [1] https://dx.doi.org/10.1093/mnras/282.4.1321

    Note: this one does not set a density, as none was found in the paper. Ricci
    et al. 2010 assume 2.5 g/cc

    Arguments:
    ----------

    sample : str
        which of the samples to use, implemented are: 'ACH2', 'BE'

    Keywords:
    ---------

    extrapol : bool
        whether or not to extrapolate beyond ~0.19 mm

    lmax : float
        upper limit for extrapolation range
    """

    def __init__(self, sample='ACH2', extrapol=False, lmin=4.765e-2, lmax=1.0):
        """
        Overwrite the initialization of the parent class
        """
        #
        # open files, read data
        #
        directory = os.path.join('optical_constants', 'zubko+1996')

        self.material_str = 'Carbonaceous Grains (Zubko et al. 1996, {})'.format(sample)
        self.datafile = directory

        E = np.loadtxt(pkg_resources.resource_filename(
            __name__, os.path.join(self.datafile, 'zubko_E_{}.txt'.format(sample))))[-1::-1]
        n = np.loadtxt(pkg_resources.resource_filename(
            __name__, os.path.join(self.datafile, 'zubko_n_{}.txt'.format(sample))))[-1::-1]
        k = np.loadtxt(pkg_resources.resource_filename(
            __name__, os.path.join(self.datafile, 'zubko_k_{}.txt'.format(sample))))[-1::-1]
        l = 0.00012398419292004205 / E  # E = h*c/lambda in CGS # noqa
        #
        # assign wavelength and optical constants
        #
        self._l = l
        self._n = n
        self._k = k
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()

        if extrapol:
            self.extrapolate_constants_up(lmin, lmax)


class diel_warren84(diel_const):
    """
    Returns the dielectric constants for water ice according to the data by
    [Warren 1984](https://dx.doi.org/10.1364/AO.23.001206). The data was taken
    from the journal website, where the coldest temperature column was used.
    """

    def __init__(self):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        self.material_str = 'Water Ice (Warren 1984)'
        #
        # set the file name
        #
        fname = 'warren_1984.txt'
        self.datafile = pkg_resources.resource_filename(
            __name__, os.path.join('optical_constants', 'warren', fname))
        if not os.path.isfile(self.datafile):
            download(self.datafile)
        #
        # read data and assign wavelength and optical constants
        #
        data = np.loadtxt(self.datafile)
        self._l = data[:, 0] * 1e-4
        self._n = data[:, 1]
        self._k = data[:, 2]
        #
        # assign derived attributes
        #
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.rho = 0.917  # Warren 1984, page 1215


class diel_warrenbrandt08(diel_const):
    """
    Returns the dielectric constants for water ice according
    to the updated water data downloaded from

        http://www.atmos.washington.edu/ice_optical_constants/

    on Jan 23, 2014, and based on [Warren & Brandt (2008)](https://dx.doi.org/10.1029/2007JD009744).
    """

    def __init__(self):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        self.material_str = 'Water Ice (Warren & Brandt 2008)'
        #
        # set the file name
        #
        fname = 'IOP_2008_ASCIItable.dat'
        self.datafile = pkg_resources.resource_filename(
            __name__, os.path.join('optical_constants', 'warren', fname))
        if not os.path.isfile(self.datafile):
            download(self.datafile)
        #
        # read data and assign wavelength and optical constants
        #
        data = np.loadtxt(self.datafile)
        self._l = data[:, 0] * 1e-4
        self._n = data[:, 1]
        self._k = data[:, 2]
        #
        # assign derived attributes
        #
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()
        self.rho = 0.917  # Warren 1984, page 1215


class diel_ricci10(diel_const):
    """
    Returns the dielectric constants from Luca Riccis files
    (cf. Ricci et al. 2010, A&A vol. 512, p. 15)

    Arguments:
    ---------
    species : string
    :    which species to return; can be silicate, ice, or carbon

    Keywords:
    ---------
    extrapol : bool
    :    whether or not to extrapolate beyond the given data up lmax (default: 10cm)

    lmax : float
    :    upper limit of extrapolation range (upper extrapolation is quadratic)

    lmin : float
    :    lower limit of extrapolation range (lower extrapolation is constant)

    Notes:
    ------
    Default is no extrapolation. If extrapol==True, the upper range will be extrapolated
    to 10 cm or the value given as lmax. Lower extrapolation (constant value) will only
    be done if a lower limit is explicitly given as lmin.

    """

    def __init__(self, species, extrapol=False, lmin=None, lmax=10.0):
        """
        Overwrite the initialization of the parent class
        """
        #
        # set the path and do some safety checks
        #
        self.material_str = ('Lucas ' + species).replace('ice', 'water ice')
        self.extrapol = extrapol
        #
        # set the file name
        #
        if species == 'silicate':
            fname = 'silicate.dat'
        elif species == 'ice':
            fname = 'H2Oice_Warren.dat'
        elif species == 'carbon':
            fname = 'aC_ACH2_Zubko.dat'
        else:
            raise NameError('%s got unknown species: %s' % (type(self).__name__, species))
        self.datafile = pkg_resources.resource_filename(
            __name__, os.path.join('optical_constants', 'luca', fname))
        #
        # read data and assign wavelength and optical constants
        #
        f = open(self.datafile)
        self.headerinfo = [f.readline() for i in range(2)]
        data = np.loadtxt(f)
        l = data[:, 0] * 1e-4 # noqa
        n = data[:, 1] + 1.0
        k = data[:, 2]
        #
        # extrapolate
        #
        if extrapol:
            #
            # UPPER EXTRAPOLATION: log-quadratic
            #
            le = np.logspace(np.log10(l[-1]), np.log10(lmax), 10)
            from scipy.optimize import curve_fit

            def f(x, a, b, c):
                return a + b * x + c * x**2

            i_min = abs(l - 1e-1).argmin()
            #
            # extrapolate n
            #
            res = curve_fit(f, np.log10(l[i_min:]), np.log10(n[i_min:]), [np.log10(n[-1]), 1, 0])
            ne = 10.**f(np.log10(le), *res[0])
            n = np.append(n, ne)
            #
            # extrapolate k
            #
            res = curve_fit(f, np.log10(l[i_min:]), np.log10(k[i_min:]), [np.log10(k[-1]), 1, 0])
            ke = 10.**f(np.log10(le), *res[0])
            k = np.append(k, ke)
            l = np.append(l, le) # noqa
            #
            # LOWER EXTRAPOLATION: constant
            #
            if lmin is not None:
                n = np.append(n[0], n)
                k = np.append(k[0], k)
                l = np.append(lmin, l) # noqa
        #
        # assign the attributes
        #
        self._l = l
        self._n = n
        self._k = k
        self._ll = np.log10(self._l)
        self._ln = np.log10(self._n)
        self._lk = np.log10(self._k)
        self._lmin = self._l.min()
        self._lmax = self._l.max()


class diel_mixed():
    """
    This is a dielectric_constant class that mixes the various
    dielectric constants given their abundances.

    Arguments:
    ----------
    constants : list of objects of class diel_const
    :    all the materials that should be mixed

    abundances : array
    :    the volume fractions for each material

    rule : str
    :    the mixing rule. Possible choices are
         'Bruggeman'
    """

    def __init__(self, constants, abundances, rule='Bruggeman', extrapol=False):
        """
        Initialize mixed dielectric constants.

        Arguments
        ---------
        constants : list
            a list of optical constants (diel_const)

        abundances : list
            volume fractions of the different constants

        rule : str
            the mixing rule; 'Bruggeman' or 'Maxwell-Garnett'

        extrapol : bool
            whether or not to extrapolate constants beyond there defined interval
        """
        if rule.lower() not in ['bruggeman', 'maxwell-garnett']:
            raise NameError('Unknown mixing rule: %s' % rule)
        if rule.lower() == 'maxwell-garnett':
            print('using Maxwell-Garnett mixing: first component should be host material (= matrix)')
            if constants[0].material_str is not None:
                print('    matrix = {}'.format(constants[0].material_str))

        self.material_str = '%s-Mix of %i species' % (rule, len(constants))
        self.constants = constants
        self.abundances = abundances
        self.rule = rule
        self.extrapol = extrapol

    def nk(self, l):
        """
        Returns the mixed optical constants at the given wavelength

        Arguments:
        ----------

        l : float or array
        :    wavelength in cm

        Output:
        -------
        n : float
        :    real part of mixed optical property

        k : float
        :    imaginary part of mixed optical property
        """
        from mpmath import findroot
        l_arr = np.array(l, ndmin=1)
        eps_mean = np.empty(np.shape(l_arr)).astype('complex')

        for i, l in enumerate(l_arr):
            #
            # calculate eps = (n + I*k)**2 for each material
            #
            eps = np.array([complex(*c.nk(l))**2 for c in self.constants])

            if self.rule.lower() == 'bruggeman':
                #
                # define the mixing rule and solve for the mixed value
                #
                def fct(x):
                    return sum(self.abundances * ((eps - x) / (eps + 2 * x)))
                eps_mean[i] = complex(findroot(fct, complex(0.5, 0.5)))
            elif self.rule.lower() == 'maxwell-garnett':
                #
                # kataoka et al. 2014, eq. 3
                #
                # fj_gammaj = np.array(self.abundances) * 3. / (eps + 2.)
                # eps_mean[i] = (fj_gammaj * eps).sum() / (fj_gammaj.sum())
                #
                # according to another paper, turns out to be equivalent
                #
                # eps_h = eps[0]
                # eps_i = eps[1:]
                # f_i = self.abundances[1:]
                # R = (f_i * (eps_i - eps_h) / (eps_i + 2 * eps_h)).sum(0)
                # eps_mean[i] = eps_h * (1 + 2 * R) / (1 - R)
                #
                # according to Bohren & Huffman
                #
                eps_m = eps[0]
                eps_i = eps[1:]
                f_i = self.abundances[1:]
                beta_i = 3 * eps_m / (eps_i + 2 * eps_m)
                f = sum(f_i)
                eps_mean[i] = ((1 - f) * eps_m + (f_i * beta_i * eps_i).sum()) / \
                    (1 - f + (f_i * beta_i).sum())
            #
            # return n and k
            #
            eps_mean = np.sqrt(eps_mean)
            return np.array([eps_mean.real.squeeze(), eps_mean.imag.squeeze()])

    def get_normal_object(self):
        """
        By default, diel_mixed provides only the nk values, when self.nk is
        called. We can make this object behave like the other optical constants
        with this function. This will return a diel_const object.
        """

        const = self.constants

        lmin = np.max([c._lmin for c in const])
        lmax = np.min([c._lmax for c in const])
        lam = np.logspace(np.log10(lmin), np.log10(lmax), 200)

        n = np.zeros_like(lam)
        k = np.zeros_like(lam)

        for i, _lam in enumerate(lam):
            n[i], k[i] = self.nk(_lam)

        d = diel_const(lam, n, k)
        d.datafile = ''

        for c in const:
            d.datafile += c.datafile + '\n'

        d.material_str = self.material_str
        d.extrapol = self.extrapol

        return d


def powerlaw_N_of_a(a, a_max, q, rho_s):
    """
    Gives the size distribution N(a) ~ a**-q, normalized to 1 g total
    mass with upper cut-off a_max.

    Arguments:
    ----------

    a : array
        the size grid in cm

    a_max : float
        the upper size cut-off in cm

    q : float
        the negative exponent, like 3.5 for MRN

    rho_s : float
        the material density in g cm**-3

    Output:
    -------
    dist : array
        the size distribution N(a)

    """
    m = 4. * np.pi / 3. * rho_s * a**3
    dist = a**-q * (a <= a_max)
    dist = dist / np.trapz(dist * m, x=a)
    return dist


def gaussian_N_of_a(a, a_mean, sigma_a, rho_s):
    """
    Gives a gaussian size distribution
    N(a) ~ exp(-(a - a_mean)**2 / (2 * sigma**2)),
    normalized to 1 g total mass.

    Arguments:
    ----------

    a : array
        the size grid in cm

    a_max : float
        the upper size cut-off in cm

    q : float
        the negative exponent, like 3.5 for MRN

    rho_s : float
        the material density in g cm**-3

    Output:
    -------
    dist : array
        the size distribution N(a)

    """
    m = 4. * np.pi / 3. * rho_s * a**3
    dist = np.exp(-(a - a_mean)**2 / (2 * sigma_a**2))
    dist = dist / np.trapz(dist * m, x=a)
    return dist


def get_kappa_from_q(a, m, q_abs, q_sca):
    """
    Converts absorption and scattering coefficients [unitless] to absorption and
    scattering opacities [cm^2/g].

    Arguments:
    ----------

    q_abs, q_sca : arrays
        absorption and scattering coefficients, shape (n_sizes, n_wavelength)

    a, m: arrays
        particle size and particle mass arrays

    Output:
    -------

    kappa_abs, kappa_sca : arrays
        opacities in units of [cm^2/g]
    """
    n_lam = q_abs.shape[1]
    kappa_abs = q_abs * np.tile(np.pi * a**2 / m, [n_lam, 1]).transpose()
    kappa_sca = q_sca * np.tile(np.pi * a**2 / m, [n_lam, 1]).transpose()
    return kappa_abs, kappa_sca


def get_size_averaged_opacity(a, lam, n, rho_s, diel_const=None, q_abs=None,
                              q_sca=None, k_abs=None, k_sca=None):
    """
    Averages the opacity over the given size distribution.

    Arguments:
    ----------

    a : array
        the size grid in cm

    lam : array
        the wavelength grid in cm

    n : array
        the size distribution N(a)

    rho_s : float
        the material density of the dust grains


    Keywords:
    ---------

    One of the following three options has to be given:

    diel_const : object of class diel_const
        the dielectric constants to be used

    q_abs,q_sca : array
        if the opacity coefficients for all sizes and wavelength has already
        been calculated, then you can pass it along, otherwise
        it will be calculated on the fly.

    q_abs,q_sca : array
        if the opacity for all sizes and wavelength has already
        been calculated, then you can pass it along, otherwise
        it will be calculated on the fly.

    Output:
    -------
    kappa_abs,kappa_sca : array
        the opacity at each wavelength averaged over the size
        distribution and normalized per 1 g of dust.
    """
    assert (diel_const is not None), "diel_const needs to be "

    if (q_abs is None or q_sca is None) and (k_abs is None or k_sca is None) \
            and (diel_const is None):
        raise AssertionError('Either (diel_const) or (q_abs, q_sca) or (k_abs, k_sca) needed as input')
    #
    # some basic conversions
    #
    m = 4. * np.pi / 3. * rho_s * a**3
    sig = n * m * a
    sig = sig / sum(sig)
    #
    # calculate the opacities ...
    #
    if (q_abs is None or q_sca is None) and (k_abs is None or k_sca is None):
        package = get_mie_coefficients(a, lam, diel_const)
        q_abs = package['q_abs']
        q_sca = package['q_sca']
    elif (k_abs is None or k_sca is None):
        kappa_abs, kappa_sca = get_kappa_from_q(a, m, q_abs, q_sca)
    #
    # ... average them over the size distribution ...
    #
    kappa_abs_m = np.zeros(len(lam))
    kappa_sca_m = np.zeros(len(lam))
    for i in np.arange(len(lam)):
        kappa_abs_m[i] = sum(np.transpose(kappa_abs[:, i]) * sig, 0)
        kappa_sca_m[i] = sum(np.transpose(kappa_sca[:, i]) * sig, 0)
    #
    # ... and return them
    #
    return kappa_abs_m, kappa_sca_m


def get_mie_coefficients(A, LAM, diel_constants, bhmie_function=bhmie_function,
                         nang=3, return_all=False, extrapolate_large_grains=False):
    """
    This calculates the opacity for the given dielectric constants for all
    grain sizes and wavelength specified in LAM and A.

    Arguments:
    ----------
    A : array
        all the grain sizes for which the opacities are calculated

    LAM : array
        all the wavelength in cm at which the opacities are calculated

    diel_constants : object of class diel_const
        the dielectric constants that are used for the calculation

    Keywords:
    ---------

    method : callable
        a function that carries out the Mie calculation with this signature
        S1, S2, Qext, Qabs, Qsca, Qback, gsca = bhmie_function(x, (n, k), n_angles)

    nang : int
        number of angles between 0 and 90 degree. Will return S1 & S2 at
        2 * nang - 1 angles between 0 and 180 degree.

    extrapolate_large_grains : bool
        default: False; if True, then extrapolate the absorption and scattering
        coefficients for very large grains.

    Output:
    -------
    Dictionary with these entries:

    q_abs,q_sca : array
        absportion and scattering coefficients

    theta : array
        angles

    g : array
        assymetry factor

    S1, S2 : arrays
        complex scattering amplitudes
    """
    from scipy.optimize import fsolve
    #
    # feed the bhmie function
    # use the first entries
    #
    q_abs = np.zeros([len(A), len(LAM)])
    q_sca = np.zeros_like(q_abs)
    g_sca = np.zeros_like(q_abs)
    s_1 = np.zeros([len(A), len(LAM), 2 * nang - 1], dtype=complex)
    s_2 = np.zeros([len(A), len(LAM), 2 * nang - 1], dtype=complex)
    NMXX = 200000  # after how many terms to use extrapolation
    full_mask = np.zeros_like(q_abs)

    # issue a warning for large size parameters

    xmax = 2. * np.pi / LAM.min() * A.max()
    xstop = xmax + 4. * xmax**.333333 + 2.0
    nmx = (xstop.max() + 15).max()
    if nmx > 2e5 and extrapolate_large_grains is False:
        warnings.warn('large size parameter: nmx={} - this can take long'.format(nmx))
    #
    # the wave length loop
    #
    for ilam, lam in enumerate(LAM):
        #
        # display progress
        #
        progress_bar((ilam + 1.0) / len(LAM) * 100, 'Mie')
        #
        # interpolate the refr. index
        #
        n, k = diel_constants.nk(lam)
        #
        # define the size parameter
        #
        X = 2. * np.pi / lam * A
        #
        # define the cutoff where no convergence is reached
        # mask is true where the calculation should converge
        #
        Y = X * (n + k * 1j)
        Y = abs(Y)
        Xstop = X + 4. * X**.333333 + 2.0
        nmx = np.maximum(Xstop, Y).astype(int) + 15
        mask = nmx < NMXX
        if extrapolate_large_grains is False:
            mask[:] = True
        full_mask[:, ilam] = mask
        #
        # cut it such that only converging terms are included
        # and extrapolate the missing parts (see below).
        # X_cut are the ones that should be calculated normally
        #
        X_cut = X[mask]
        if len(X_cut) == 0:
            def f(x):
                return x + 4. * x**0.33333 + 2.0 - NMXX
            x_max = fsolve(f, NMXX)  # /30.
            X_cut = [x_max]
        #
        # loop through the sizes that converge
        #
        for ia, x in enumerate(X_cut):
            S1, S2, Qext, Qabs, Qsca, Qback, gsca = bhmie_function(x, complex(n, k), nang)
            q_abs[ia, ilam] = Qabs
            q_sca[ia, ilam] = Qsca
            g_sca[ia, ilam] = gsca.real
            s_1[ia, ilam, :] = S1
            s_2[ia, ilam, :] = S2
        #
        # extrapolate for large grains
        #
        q_abs[ia + 1:, ilam] = q_abs[ia, ilam]
        q_sca[ia + 1:, ilam] = q_sca[ia, ilam]

        # Laor & Draine 1993, Eq. 8

        g_sca[ia + 1:, ilam] = 0.3 * X[ia + 1:]**2 / (1 + 0.3 * X[ia + 1:]**2)  # g_sca[ia, ilam]

    package = {
        'q_abs': q_abs,
        'q_sca': q_sca,
        'g': g_sca,
        'S1': s_1,
        'S2': s_2,
        'theta': np.linspace(0, 180., 2 * nang - 1)
        }

    package['info'] = """Created with the disklab package by Kees Dullemond and Til Birnstiel.
    If you make use of this file or package, do cite the according paper
    Dullemond & Birnstiel 2018.
    """

    return package


def calculate_mueller_matrix(lam, m, S1, S2):
    """
    Calculate the Mueller matrix elements given the scattering amplitudes
    S1 and S2.

    Arguments:
    ----------

    lam : array
        wavelength array of length nlam

    m : array
        particle mass array of length nm

    S1, S2 : arrays
        scattering amplitudes of shape (nm, nlam, nangles), where
        nangles is the length of the angle array for which the amplitudes
        were calculated.

    Notes:
    ------
    The conversion factor `factor` is calculated as defined in Kees Dullemonds
    code `makeopac.py`:
    > Compute conversion factor from the Sxx matrix elements
    > from the Bohren & Huffman code to the Zxx matrix elements we
    > use (such that 2*pi*int_{-1}^{+1}Z11(mu)dmu=kappa_scat).
    > This includes the factor k^2 (wavenumber squared) to get
    > the actual cross section in units of cm^2 / ster, and there
    > is the mass of the grain to get the cross section per gram.
    """
    factor = (lam[None, :] / (2 * np.pi))**2 / m[:, None]
    #
    # Compute the scattering Mueller matrix elements at each angle
    #
    S11 = 0.5 * (np.abs(S2)**2 + np.abs(S1)**2)
    S12 = 0.5 * (np.abs(S2)**2 - np.abs(S1)**2)
    S33 = np.real(S2[:] * np.conj(S1[:]))
    S34 = np.imag(S2[:] * np.conj(S1[:]))

    zscat = np.zeros([len(m), len(lam), S1.shape[-1], 6])

    zscat[..., 0] = S11 * factor[:, :, None]
    zscat[..., 1] = S12 * factor[:, :, None]
    zscat[..., 2] = S11 * factor[:, :, None]
    zscat[..., 3] = S33 * factor[:, :, None]
    zscat[..., 4] = S34 * factor[:, :, None]
    zscat[..., 5] = S33 * factor[:, :, None]

    return zscat


def make_opacity_dict(lam, a, k_abs, k_sca, g_sca, rho_s, zscat=None):
    """
    To mimick the behavior of the `makedustopac.py` code by Kees Dullemond:
    package the opacity information to a dictionary.
    """
    package = {
        'lamcm': lam,
        'kabs': k_abs,
        'kscat': k_sca,
        'gscat': g_sca,
        'rho_s': rho_s,
        'a': a,
        'zscat': zscat
        }

    return package


def write_disklab_opacity(fname, opac_dict, dir='.'):
    """
    Write the output of a Mie opacity calculation to a file. Minimum requirement
    is particle size and wavelength grid along with the according absorption and
    scattering opacities [cm^2/g].

    Arguments:
    ----------

    fname : str
        file name under which to store the data

    opac_dict : dict
        opacity information. needs to have:
            a : array
                particle size array [cm]

            lam : array
                wavelength array [cm]

            k_abs, k_sca : arrays
                absorption and scattering opacities shape = (len(a), len(lam))
        Optional:
            g : array
                Henyey-Greenstein anisotropy factor, shape = k_abs.shape

            rho_s : array
                material density of the grains

    Keywords:
    ---------

    dir : str
        path where to store the file, defaults to current directory
    """

    assert 'a' in opac_dict, 'opacity dictionary needs to contain particle size array \'a\''
    assert 'lam' in opac_dict, 'opacity dictionary needs to contain wave length array \'lam\''
    assert 'k_abs' in opac_dict, 'opacity dictionary needs to contain absortpion opacity array \'k_abs\''
    assert 'k_sca' in opac_dict, 'opacity dictionary needs to contain scattering opacity array \'k_sca\''

    # build a dict that contains only the data we need

    dictionary = {}
    dictionary['a']     = opac_dict['a']
    dictionary['lam']   = opac_dict['lam']
    dictionary['k_abs'] = opac_dict['k_abs']
    dictionary['k_sca'] = opac_dict['k_sca']
    if 'g' in opac_dict:
        dictionary['g'] = opac_dict['g']
    if 'rho_s' in opac_dict:
        dictionary['rho_s'] = opac_dict['rho_s']
    if 'info' in opac_dict:
        dictionary['info'] = opac_dict['info']

    np.savez_compressed(os.path.join(dir, fname), **dictionary)


def write_radmc3d_scatmat_file(index, opacity_dict, name, dir='.'):
    """
    The RADMC-3D radiative transfer package[1] can perform dust continuum
    radiative transfer for diagnostic purposes. It is designed for astronomical
    applications. The code needs the opacities in a particular form. This
    subroutine writes the opacities out in that form. It will write it to
    the file dustkapscatmat_<name>.inp.

    Arguments:
    ----------

    index : int
        index of the grain species to be written out

    opacity_dict : dict
        dictionary with the opacity information. the keys are:

        a : array
            particle size grid in cm

        lam : array
            wavelength grid in cm

        theta : array
            angle grid (degree)

        rho_s : float
            internal density of the particles

        k_abs, k_sca : array
            absorption and scattering opacities
            size = len(a), len(lam)

        g_scat : array
            Henyey-Greenstein coefficient
            size = len(a), len(lam)

        zscat : array
            scattering Mueller matrix elements
            size = len(a), len(lam), len(theta), 6


    References:
    -----------

    - [1] http://www.ita.uni-heidelberg.de/~dullemond/software/radmc-3d/

    """
    filename = os.path.join(dir, 'dustkapscatmat_{}.inp'.format(name))

    with open(filename, 'w') as f:
        f.write('# Opacity and scattering matrix file for ' + name + '\n')
        f.write('# Please do not forget to cite in your publications theoriginal paper of these optical constant measurements\n')
        f.write('# Made with the DISKLAB package code by Cornelis Dullemond & Til Birnstiel\n')
        f.write('# using the bhmie.py Mie code of Bohren and Huffman (python version by Cornelis Dullemond,')
        f.write('# F90 version by Til Birnstiel, both after the original bhmie.f code by Bruce Draine)\n')
        f.write('# Grain size = {0:13.6e} cm\n'.format(opacity_dict["a"]))
        f.write('# Material density = {0:6.3f} g/cm^3\n'.format(opacity_dict["rho_s"]))
        f.write('1\n')  # Format number
        f.write('{0:d}\n'.format(opacity_dict["lam"].size))
        f.write('{0:d}\n'.format(opacity_dict["theta"].size))
        f.write('\n')
        for i in range(opacity_dict['lam'].size):
            f.write('%13.6e %13.6e %13.6e %13.6e\n' % (opacity_dict['lam'][i] * 1e4,
                                                       opacity_dict['k_abs'][i],
                                                       opacity_dict['k_scat'][i],
                                                       opacity_dict['g_scat'][i]))
        f.write('\n')
        for j in range(opacity_dict['theta'].size):
            f.write('%13.6e\n' % (opacity_dict['theta'][j]))
        f.write('\n')
        for ilam in range(opacity_dict['lam'].size):
            for itheta in range(opacity_dict['theta'].size):
                f.write('%13.6e %13.6e %13.6e %13.6e %13.6e %13.6e\n' %
                        (opacity_dict['zscat'][ilam, itheta, 0], opacity_dict['zscat'][ilam, itheta, 1],
                         opacity_dict['zscat'][ilam, itheta, 2], opacity_dict['zscat'][ilam, itheta, 3],
                         opacity_dict['zscat'][ilam, itheta, 4], opacity_dict['zscat'][ilam, itheta, 5]))
        f.write('\n')


def compare_nk(constants, lmin=1e-5, lmax=1e3, orig_data=False, ax=None, twoaxes=True):
    """
    Compares the dielectric functions c1 and c2 (their n and k values)
    by plotting them on the range from amin to amax.

    Keywords:
    ---------

    constants : list of instances of diel_constant
        the dielectric constants to compare

    lmin : float
    :    lower bound of the plotting range

    lmax : float
    :    upper bound of the plotting range

    Keywords:
    ---------

    orig_data : bool
        if true, then just plot the original data of each object

    ax : None | plt.axes | list
        ax = None: create new figure/axes
        ax = plt.axes, plot into these axes, if twoaxes=True, add twin axis
        ax = list: plot into those axes, then twoaxes=True automatically

    twoaxes : bool
        if true, then use two different y axes for n and k

    Output:
    -------
    A plot comparing both optical property functions
    """
    import matplotlib.pyplot as plt

    nlam = 100
    lam = np.logspace(np.log10(lmin), np.log10(lmax), nlam)

    if ax is None:
        f, ax = plt.subplots()

    if isinstance(ax, (list, np.ndarray)):
        ax1 = ax[0]
        ax2 = ax[1]
        twoaxes = True
    else:
        ax1 = ax
        if twoaxes:
            ax2 = plt.twinx(ax1)
        else:
            ax2 = ax1

    lines = []

    for n, c in enumerate(constants):
        nk = np.zeros([len(lam), 2])

        if orig_data and (c._n is not None) and (c._l is not None):
            lam = c._l
            nk = np.array([c._n, c._k]).T
        else:
            for i in np.arange(nlam):
                try:
                    nk[i] = c.nk(lam[i])
                except BaseException:
                    nk[i] = np.nan

        mask = np.invert(np.isnan(nk[:, 0]))
        lines += ax1.loglog(lam[mask], nk[:, 0][mask], label='$n_1$ - {}'.format(c.material_str), alpha=0.7, ls='-')
        mask = np.invert(np.isnan(nk[:, 1]))
        lines += ax2.loglog(lam[mask], nk[:, 1][mask], label='$k_1$ - {}'.format(c.material_str), c=lines[-1].get_color(), alpha=0.7, ls='--')

    ax1.set_xlabel('wavelength [cm]')
    if twoaxes:
        ax1.set_ylabel('$n$')
        ax2.set_ylabel('$k$')
        ax1.set_yscale('linear')
    else:
        ax1.set_ylabel('$n, k$')

    ax1.legend(lines, [l.get_label() for l in lines], loc='best', fontsize='xx-small')

    if twoaxes:
        return ax1, ax2
    else:
        return ax1


def get_dsharp_mix(fm_ice=0.2, rule='Bruggeman'):
    """
    This method calculates the mixed mie coefficients for the DSHARP project.

    The densities and volume fractions are based on D'Alessio et al. 2001, 2006.
    However newer optical constants are used and the water fraction comes from
    Rosetta measurements.

    |                 | water ice | astrosilicates | troilite    | organics  |
    |:---------------:|:---------:|:--------------:|:-----------:|:---------:|
    | volume fraction | 0.5737    | 0.1120         | 0.0173      | 0.2970    |
    | solid densities | 0.92 g/cc | 3.3 g/cc       | 4.83 g/cc   | 1.5 g/cc  |

    Keywords:
    ---------

    fm_ice : float
        mass fraction of water ice.

    rule : str
        'Bruggeman' or 'Maxwell-Garnett'. Ricci et al. 2010 used 'Bruggeman'.

    Output:
    -------

    diel_constants : object of class diel_const
        the mixed dielectric constants

    rho_s : float
        the material density of the particles in g/cm**3
    """
    # define arrays for optical constants, bulk densities, and volume fractions for each species

    constants = [
        diel_warrenbrandt08(),
        diel_draine2003('astrosilicates'),
        diel_henning('troilite'),
        diel_henning('organics'),
        ]

    # material densities

    densities = np.array([
        0.92,
        3.30,
        4.83,
        1.50])

    # fm_rest is the normalized mass fractions of the rest (adding up to 1)

    fm_rest = np.array([0.41127, 0.09292, 0.49581])
    f_mass = np.hstack((
        fm_ice,
        (1 - fm_ice) * fm_rest))

    # calculate the mean density, needed to get opacity in units of cm^2/g

    rho_s = 1.0 / (f_mass / densities).sum()

    f_vol = rho_s / densities * f_mass
    f_vol = f_vol / f_vol.sum()

    length = max([len(c.material_str) for c in constants])
    length = max([length, 16])

    print('| material'.ljust(length + 2) + '| volume fractions | mass fractions |')
    print('|' + (length + 1) * '-' + '|' + 18 * '-' + '|' + 16 * '-' + '|')
    for c, fv, fm in zip(constants, f_vol, f_mass):
        print(
            '| ' +
            c.material_str.ljust(length) +
            '| {:.4}'.format(fv).ljust(19) +
            '| {:.4}'.format(fm).ljust(17) + '|')

    # mix the optical constants using the Bruggeman rule

    return diel_mixed(constants, f_vol, rule=rule), rho_s


def get_ricci_mix(extrapol=False, lmax=None, rule='Bruggeman'):
    """
    This method calculates the mixed mie coefficients as in Ricci et al. 2010.

    The densities and volume fractions stated in Ricci et al. 2010 contained
    typos. The values used here come from L. Ricci, private communications.

    |                 | vacuum | silicates |  carbonaceous | water ice |
    |:---------------:|:------:|:---------:|:-------------:|:---------:|
    | volume fraction | 0.30   | 0.07      |     0.21      |    0.42   |
    | solid densities | 0 g/cc | 3.5 g/cc  |    2.5 g/cc   |  1 g/cc   |

    Keywords:
    ---------

    extrapol : bool
        whether the optical constants do extrapolation or not

    rule : str
        'Bruggeman' or 'Maxwell-Garnett'. Ricci et al. 2010 used 'Bruggeman'.

    Output:
    -------

    diel_constants : object of class diel_const
        the mixed dielectric constants

    rho_s : float
        the material density of the particles in g/cm**3
    """
    if extrapol and (lmax is None):
        raise ValueError('need to set lmax if extrapol is True')

    c0 = diel_vacuum()
    c1 = diel_draine2003('astrosilicates')
    c2 = diel_zubko96(extrapol=extrapol, lmax=lmax)
    c3 = diel_warrenbrandt08()

    constants = [c0, c1, c2, c3]

    # after Lucas thesis, the fractions in Ricci+2010 are typos

    vol_fract = [0.30, 0.07, 0.21, 0.42]
    densities = [0.00, 3.50, 2.50, 1.00]

    diel_constants = diel_mixed(constants, vol_fract, rule=rule)
    rho_s = sum(densities * np.array(vol_fract))

    return diel_constants, rho_s


def get_opacities(a, lam, rho_s=None, diel_const=None, bhmie_function=bhmie_function,
                  return_all=False, extrapol=False, n_angle=3,
                  extrapolate_large_grains=False):
    """
    Calculates opacities according to some specified method for
    a given size- and wavelength grid. If diel_const and rho_s is not given,
    default opacities are used. Otherwise both rho_s and diel_const are needed.

    Arguments:
    ----------

    a : array
        The grain size grid in cm

    lam : array
        the wavelength grid in cm

    Keywords:
    ---------

    diel_const : dielectric constant
        in case other dielectric constants should be used

    rho_s : float
        material density of each size [g/cm^3]

    bhmie_function : callable
        which function to use for the mie calculation

    extrapol : bool
        whether to extrapolate *default* optical constants if lam is outside the
        wavelength range of the data

    n_angle : int
        number of angles for which to calculate scattering properties

    extrapolate_large_grains : bool
        option passed to get_mie_cofefficients, see there.

    Output:
    -------
    Returns a dictionary with the following entries:

    kappa_abs, kappa_sca : arrays
        absorption and scattering opacities [g/cm^2]

    theta : array
        angle (in degree, 0=forward) on which angle dependent quantities are defined

    g : array
        Henyey-Greenstein scattering asymmetry factor

    S1, S2 : arrays
        the complex scattering amplitudes

    rho_s : float
        material density of the grains [g/cm^3]

    a : array
        The grain size grid in cm

    lam : array
        the wavelength grid in cm

    """
    if (diel_const is None and rho_s is not None) or (diel_const is not None and rho_s is None):
        raise AssertionError('diel_const and rho_s need to be both given or both be None')

    if diel_const is None and rho_s is None:
        if extrapol:
            print('Note: wavelength range outside data. Extrapolation will be done but is uncertain.')
        print('Note: no dielectric constants given, will use Ricci-2010-like optical constants')
        diel_const, rho_s = get_ricci_mix(extrapol=extrapol, lmax=lam[-1])

    m = 4 * np.pi / 3. * rho_s * a**3

    package = get_mie_coefficients(
        a, lam, diel_const, return_all=True,
        bhmie_function=bhmie_function, nang=n_angle,
        extrapolate_large_grains=extrapolate_large_grains)

    q_abs = package['q_abs']
    q_sca = package['q_sca']

    kappa_abs, kappa_sca = get_kappa_from_q(a, m, q_abs, q_sca)

    package['rho_s'] = rho_s
    package['k_abs'] = kappa_abs
    package['k_sca'] = kappa_sca

    package['a'] = a
    package['lam'] = lam

    return package


def size_average_opacity(lam_avg, a, lam, k_abs, k_sca, q=3.5, plot=False, ax=None):
    """
    Calculates the opacity as function of maximum particle size for a power-law size distribution

    Arguments:
    ----------
    lam_avg : float | array
        wavelength at which to calculate the size-averaged opacities
        if a 2 element array is given, also beta will be calculatedself. The size
        averaged opacity of the first wavelength will be returned/plotted

    a : array
        particle size array [cm]

    lam : array
        wavelength array [cm]

    k_abs, k_sca: arrays
        absoprtion and scattering opacitity [cm^2/g]

    Keywords:
    ---------

    q : float
        power-law index of the size distribution, n(a) \propto a^{-q}

    plot : bool
        if True, create a plot of the result

    ax : None | axes object
        if None: plot is created in new figure, if axes object: uses this object
        for the plotting.

    Output:
    -------
    k_abs, k_sca, [ax]

    k_abs, k_sca : arrays
        size averaged opacities as function of maximum particle size

    ax : axes object
        if plot is True: return the axes object
    """
    import matplotlib.pyplot as plt

    # interpolate at the observed frequencies
    lam_avg = np.array(lam_avg, ndmin=1)
    if len(lam_avg) > 1:
        calc_beta = True
    else:
        calc_beta = False

    k_a = []
    k_s = []

    for _lam in lam_avg:
        k_a += [[np.interp(_lam, lam, k_abs[ia, :]) for ia in range(len(a))]]
        k_s += [[np.interp(_lam, lam, k_sca[ia, :]) for ia in range(len(a))]]

    k_a = np.array(k_a)
    k_s = np.array(k_s)

    # average over size distributions

    ka = np.zeros([len(lam_avg), len(a)])
    ks = np.zeros([len(lam_avg), len(a)])
    for ia in range(len(a)):

        # make a size distribution

        s = (a / a[0])**(4 - q)
        if ia < len(a) - 1:
            s[ia + 1:] = 1e-100
        s = s / s.sum()

        for ilam in range(len(lam_avg)):
            ka[ilam, ia] = np.sum(k_a[ilam, :] * s)
            ks[ilam, ia] = np.sum(k_s[ilam, :] * s)

    ret = {'ka': ka, 'ks': ks}

    # calculate beta

    if calc_beta:
        beta = -np.log10(ka[-1, :] / ka[0, :]) / np.log10(lam_avg[-1] / lam_avg[0])
        ret['beta'] = beta

    if plot:
        if ax is None:
            f, ax = plt.subplots()
        ax = np.array(ax, ndmin=1)
        lines = []
        lines += ax[0].loglog(a, ka[0, :], '-', label='absorption, $\lambda = {:2.2g}$ mm'.format(lam_avg[0] * 10))
        lines += ax[0].loglog(a, ks[0, :], '--', label='scattering, $\lambda = {:2.2g}$ mm'.format(lam_avg[0] * 10))
        ax[0].set_xlabel('$a_\mathrm{max}$ [cm]')
        ax[0].set_ylabel('$\kappa$ [cm$^2$/g]')
        ax[0].set_xlim(1e-4, 1e2)
        ax[0].set_ylim(0.01, 50)

        one_leg = True
        lines2 = []
        if calc_beta:
            if len(ax) == 2:
                ax2 = ax[1]
                ax2.set_xlabel('$a_\mathrm{max}$ [cm]')
                one_leg = False
            else:
                ax2 = plt.twinx(ax[0])

            lines2 += ax2.semilogx(a, beta, 'k-', label=r'$\beta$')
            ax2.set_ylabel(r'$\beta$')
            ax2.set_ylim(0, 4)
            ret['ax2'] = ax2

        if one_leg:
            lines += lines2
            ax[0].legend(lines, [_l.get_label() for _l in lines])
        else:
            ax[0].legend(lines, [_l.get_label() for _l in lines])
            ax2.legend(lines2, [_l.get_label() for _l in lines2])

        ret['ax1'] = ax[0]

    return ret