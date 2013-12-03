# -*- coding: utf-8 -*-

# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Implementations restoration functions"""

from __future__ import division

import numpy as np
import numpy.random as npr
from scipy.signal import convolve2d

from . import uft

__credits__ = ["François Orieux"]
__license__ = "mit"
__version__ = "1.0.0"
__maintainer__ = "François Orieux"
__status__ = "stable"
__keywords__ = "restoration, image, deconvolution"


def wiener(image, psf, balance, reg=None, is_real=True):
    """Wiener-Hunt deconvolution

    Return the deconvolution with a wiener-Hunt approach (ie with
    Fourier diagonalisation).

    Parameters
    ----------
    image : (M, N) ndarray
       Input degraded image
    psf : ndarray
       The impulse response (input image's space) or the transfer
       function (Fourier space). Both are accepted. The transfer
       function is recognize as being complex (`np.iscomplex(psf)`).
    balance : float
       The regularisation parameter value that tune the balance
       between the data and the prior information.
    reg : ndarray, optional
       The regularisation operator. The Laplacian by default. It can
       be an impulse response or a transfer function, as for the psf.
    is_real : boolean, optional
       True by default. Specify if `psf` and `reg` are provided with
       hermitian hypothesis, that is only half of the frequency plane
       is provided (due to the redundancy of Fourier transform of real
       signal). It's apply only if `psf` and/or `reg` are provided as
       transfer function.  For the hermitian property see `uft`
       module or `np.fft.rfftn`.

    Returns
    -------
    im_deconv : (M, N) ndarray
       The deconvolved image

    Examples
    --------
    >>> from skimage import color, data, restoration
    >>> lena = color.rgb2gray(data.lena())
    >>> from scipy.signal import convolve2d
    >>> psf = np.ones((5, 5)) / 25
    >>> lena = convolve2d(lena, psf, 'same')
    >>> lena += 0.1 * lena.std() * np.random.standard_normal(lena.shape)
    >>> deconvolved_lena = restoration.wiener(lena, psf, 1100)

    Notes
    -----
    This function applies the Wiener filter to a noisy and degraded
    image by an impulse response (or PSF). If the data model is

    .. math:: y = Hx + n

    where :math:`n` is noise, :math:`H` the PSF and :math:`x` the
    unknown original image, the Wiener filter is

    .. math:: \hat x = F^\dag (|\Lambda_H|^2 + \lambda |\Lambda_D|^2) \Lambda_H^\dag F y

    where :math:`F` and :math:`F^\dag` are the Fourier and inverse
    Fourier transfroms respectively, :math:`\Lambda_H` the transfer
    function (or the Fourier transfrom of the PSF, see [2]) and
    :math:`\Lambda_D` the filter to penalize the restored image
    frequencies (Laplacian by default, that is penalization of high
    frequency). The parameter :math:`\lambda` tunes the balance
    between the data (that tends to increase high frequency, even
    those coming from noise), and the regularization.

    These methods are then specific to a prior model. Consequently,
    the application or the true image nature must corresponds to the
    prior model. By default, the prior model (Laplacian) introduce
    image smoothness or pixel correlation. It can also be interpreted
    as high-frequency penalization to compensate noise amplification
    or so called "explosive" solution. These methods are well
    interpreted by Bayesian analysis.
    
    Finally, the use of Fourier space implies a circulant property of
    :math:`H`, see [2].

    References
    ----------
    .. [1] François Orieux, Jean-François Giovannelli, and Thomas
           Rodet, "Bayesian estimation of regularization and point
           spread function parameters for Wiener-Hunt deconvolution",
           J. Opt. Soc. Am. A 27, 1593-1607 (2010)

           http://www.opticsinfobase.org/josaa/abstract.cfm?URI=josaa-27-7-1593

           http://research.orieux.fr/files/papers/OGR-JOSA10.pdf

    .. [2] B. R. Hunt "A matrix theory proof of the discrete
           convolution theorem", IEEE Trans. on Audio and
           Electroacoustics, vol. au-19, no. 4, pp. 285-288, dec. 1971

    """
    if reg is None:
        reg, _ = uft.laplacian(image.ndim, image.shape)
    if not np.iscomplex(reg):
        reg = uft.ir2tf(reg, image.shape)

    if psf.shape != reg.shape:
        trans_func = uft.ir2tf(psf, image.shape)
    else:
        trans_func = psf

    wiener_filter = np.conj(trans_func) / (np.abs(trans_func)**2 +
                                           balance * np.abs(reg)**2)
    if is_real:
        return uft.uirfft2(wiener_filter * uft.urfft2(image))
    else:
        return uft.uifft2(wiener_filter * uft.ufft2(image))


def unsupervised_wiener(image, psf, reg=None, user_params=None):
    """Unsupervised Wiener-Hunt deconvolution

    Return the deconvolution with a Wiener-Hunt approach, where the
    hyperparameters are estimated. The algorithm is a stochastic
    iterative process (Gibbs sampler) described in [1].

    Parameters
    ----------
    image : (M, N) ndarray
       The input degraded image
    psf : ndarray
       The impulse response (input image's space) or the transfer
       function (Fourier space). Both are accepted. The transfer
       function is recognize as being complex (`np.iscomplex(psf)`).
    reg : ndarray, optional
       The regularisation operator. The Laplacian by default. It can
       be an impulse response or a transfer function, as for the psf.
    user_params : dict
       dictionary of gibbs parameters. See below.

    Returns
    -------
    x_postmean : (M, N) ndarray
       The deconvolved image (the posterior mean).
    chains : dict
       The keys 'noise' and 'prior' contain the chain list of noise and
       prior precision respectively.

    Other parameters
    ----------------
    The keys of `user_params` are:

    threshold : float
       The stopping criterion: the norm of the difference between to
       successive approximated solution (empirical mean of object
       samples). 1e-4 by default.
    burnin : int
       The number of sample to ignore to start computation of the
       mean. 100 by default.
    min_iter : int
       The minimum number of iterations. 30 by default.
    max_iter : int
       The maximum number of iterations if `threshold` is not
       satisfied. 150 by default.
    callback : None
       A user provided callable to which is passed, if the function
       exists, the current image sample. This function can be used to
       store the sample, or compute other moments than the mean. It
       has no influence on the algorithm execution.

    Examples
    --------
    >>> from skimage import color, data, restoration
    >>> lena = color.rgb2gray(data.lena())
    >>> from scipy.signal import convolve2d
    >>> psf = np.ones((5, 5)) / 25
    >>> lena = convolve2d(lena, psf, 'same')
    >>> lena += 0.1 * lena.std() * np.random.standard_normal(lena.shape)
    >>> deconvolved_lena = restoration.unsupervised_wiener(lena, psf)

    References
    ----------
    .. [1] François Orieux, Jean-François Giovannelli, and Thomas
           Rodet, "Bayesian estimation of regularization and point
           spread function parameters for Wiener-Hunt deconvolution",
           J. Opt. Soc. Am. A 27, 1593-1607 (2010)

           http://www.opticsinfobase.org/josaa/abstract.cfm?URI=josaa-27-7-1593

           http://research.orieux.fr/files/papers/OGR-JOSA10.pdf
    """
    params = {'threshold': 1e-4, 'max_iter': 200,
              'min_iter': 30, 'burnin': 15, 'callback': None}
    params.update(user_params or {})

    if not reg:
        reg, _ = uft.laplacian(image.ndim, image.shape)
    if not np.iscomplex(reg):
        reg = uft.ir2tf(reg, image.shape)

    if psf.shape != reg.shape:
        trans_fct = uft.ir2tf(psf, image.shape)
    else:
        trans_fct = psf

    # The mean of the object
    x_postmean = np.zeros(trans_fct.shape)
    # The previous computed mean in the iterative loop
    prev_x_postmean = np.zeros(trans_fct.shape)

    # Difference between two successive mean
    delta = np.NAN

    # Initial state of the chain
    gn_chain, gx_chain = [1], [1]

    # The correlation of the object in Fourier space (if size is big,
    # this can reduce computation time in the loop)
    areg2 = np.abs(reg)**2
    atf2 = np.abs(trans_fct)**2

    # The Fourier transfrom may change the image.size attribut, so we
    # store it.
    image_size = image.size
    image = uft.urfft2(image.astype(np.float))

    # Gibbs sampling
    for iteration in range(params['max_iter']):
        # Sample of Eq. 27 p(circX^k | gn^k-1, gx^k-1, y).

        # weighing (correlation in direct space)
        precision = gn_chain[-1] * atf2 + gx_chain[-1] * areg2  # Eq. 29
        excursion = np.sqrt(0.5) / np.sqrt(precision) * (
            np.random.standard_normal(image.shape) +
            1j * np.random.standard_normal(image.shape))

        # mean Eq. 30 (RLS for fixed gn, gamma0 and gamma1 ...)
        wiener_filter = gn_chain[-1] * np.conj(trans_fct) / precision

        # sample of X in Fourier space
        x_sample = wiener_filter * image + excursion
        if params['callback']:
            params['callback'](x_sample)

        # sample of Eq. 31 p(gn | x^k, gx^k, y)
        gn_chain.append(npr.gamma(image_size / 2,
                                  2 / uft.image_quad_norm(image - x_sample *
                                                          trans_fct)))

        # sample of Eq. 31 p(gx | x^k, gn^k-1, y)
        gx_chain.append(npr.gamma((image_size - 1) / 2,
                                  2 / uft.image_quad_norm(x_sample * reg)))

        # current empirical average
        if iteration > params['burnin']:
            x_postmean = prev_x_postmean + x_sample

        if iteration > (params['burnin'] + 1):
            current = x_postmean / (iteration - params['burnin'])
            previous = prev_x_postmean / (iteration - params['burnin'] - 1)

            delta = np.sum(np.abs(current - previous)) / \
                np.sum(np.abs(x_postmean)) / (iteration - params['burnin'])

        prev_x_postmean = x_postmean

        # stop of the algorithm
        if (iteration > params['min_iter']) and (delta < params['threshold']):
            break

    # Empirical average \approx POSTMEAN Eq. 44
    x_postmean = x_postmean / (iteration - params['burnin'])
    x_postmean = uft.uirfft2(x_postmean)

    return (x_postmean, {'noise': gn_chain, 'prior': gx_chain})


def richardson_lucy(image, psf, iterations=50):
    """Richardson-Lucy deconvolution.

    Parameters
    ----------
    image : ndarray
       Input degraded image
    psf : ndarray
       The point spread function
    iterations : int
       Number of iterations. This parameter play to role of regularisation.

    Returns
    -------
    im_deconv : ndarray
       The deconvolved image

    Examples
    --------
    >>> from skimage import color, data, restoration
    >>> camera = color.rgb2gray(data.camera())
    >>> from scipy.signal import convolve2d
    >>> psf = np.ones((5, 5)) / 25
    >>> camera = convolve2d(camera, psf, 'same')
    >>> camera += 0.1 * camera.std() * np.random.standard_normal(camera.shape)
    >>> deconvolved = restoration.richardson_lucy(camera, psf, 5)

    References
    ----------
    .. [2] http://en.wikipedia.org/wiki/Richardson%E2%80%93Lucy_deconvolution

    """
    image = image.astype(np.float)
    psf = psf.astype(np.float)
    im_deconv = 0.5 * np.ones(image.shape)
    psf_mirror = psf[::-1, ::-1]
    for _ in range(iterations):
        relative_blur = image / convolve2d(im_deconv, psf, 'same')
        im_deconv *= convolve2d(relative_blur, psf_mirror, 'same')

    return im_deconv
