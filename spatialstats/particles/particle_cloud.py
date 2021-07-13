"""
Routines to calculate a spatial distribution function
:math:`g(r, \\phi, \\theta)` for point and rod-like particles.
Can reduce to the usual :math:`g(r)` with the corresponding isotropic
structure factor :math:`S(q)`.

See `here<https://en.wikipedia.org/wiki/Radial_distribution_function>_`
to learn more.

Adapted from https://github.com/wenyan4work/point_cloud.

.. moduleauthor:: Michael O'Brien <michaelobrien@g.harvard.edu>

"""

import numpy as np
import scipy.spatial as spatial
import numba as nb
from scipy.integrate import simps
from scipy.special import jv
from time import time


def structure_factor(gr, r, N, boxsize, q=None, **kwargs):
    """
    Calculate the isotropic structure factor :math:`S(q)` from
    the radial distribution function :math:`g(r)` of a set of :math:`N` 
    particle positions in a 2D or 3D periodic box with volume :math:`V`.

    The structure factor in 3D is computed as

    .. math::

        S(q) = 1 + 4\\pi \\rho \\frac{1}{q} \int dr \ r \ \\textrm{sin}(qr) [g(r) - 1]

    and in 2D

    .. math::

        S(q) = 1 + 2\\pi \\rho \int dr \ r \ J_{0}(qr) [g(r) - 1],

    where :math:`\\rho = N/V` and :math:`J_{0}` is the 0th bessel function of the first kind.

    Parameters
    ----------
    gr : `np.ndarray`
        The radial distribution function :math:`g(r)` from
        :ref:`spatialstats.particles.sdf<sdf>`.
    r : `np.ndarray`
        The domain of :math:`g(r)` from
        :ref:`spatialstats.particles.sdf<sdf>`.
    N : `int`
        The number of particles :math:`N`.
    boxsize : `list` of `float`
        The rectangular domain over which
        to apply periodic boundary conditions.
        See ``scipy.spatial.cKDTree``.
    q : `np.ndarray`, optional
        Dimensional wavenumber bins :math:`q`.
        If ``None``, ``q = np.arange(dq, 200*dq, dq)``
        with ``dq = 2*np.pi / max(boxsize)``.

    Returns
    -------
    Sq : `np.ndarray`
        The structure factor :math:`S(q)`.
    q : `np.ndarray`
        Wavenumber bins :math:`q`.
    """
    ndim = len(boxsize)

    if ndim not in [2, 3]:
        raise ValueError("Dimension of space must be 2 or 3")

    # Generate wavenumbers
    if q is None:
        dq = (2*np.pi / max(boxsize))
        q = np.arange(dq, 200*dq, dq)

    def S(q):
        '''Integrand for isotropic structure factor'''
        rho = N/np.prod(boxsize)
        if ndim == 3:
            f = np.sin(q*r)*r*(gr-1)
            return 1+4*np.pi*rho*simps(f, r)/q
        else:
            f = jv(0, q*r)*r*(gr-1)
            return 1+2*np.pi*rho*simps(f, r)

    # Integrate for all q
    Sq = []
    for j in range(len(q)):
        Sq.append(S(q[j]))
    Sq = np.array(Sq)

    return Sq, q


def sdf(positions, boxsize, orientations=None,
        rmin=None, rmax=None, nr=100, nphi=None, ntheta=None, bench=False):
    """
    .. _sdf:

    Calculate the spatial distribution function
    :math:`g(r, \\phi)` or :math:`g(r, \\phi, \\theta)`
    for a set of :math:`N` point-like or rod-like particles
    :math:`\\mathbf{r}_i` in a 2D or 3D periodic box.
    :math:`(r, \\phi, \\theta)` are the spherical coordinates for
    displacement vectors between particle pairs
    :math:`\\mathbf{r}_{ij} = \\mathbf{r}_i - \\mathbf{r}_j`.
    :math:`\\phi` is the azimuthal angle and :math:`\\theta` is
    the inclination angle.

    If particles orientations :math:`\\mathbf{p}_i` are included,
    instead define :math:`\\phi` as the angle in the
    coordinate system with :math:`\\mathbf{p}_i` pointed in the
    :math:`+y` direction in 2D or :math:`+z` direction in 3D.

    .. note::
        Reduces to the 1D distribution function :math:`g(r)`
        when ``nphi = None`` and ``ntheta = None``.

    Parameters
    ---------
    positions : `np.ndarray`, shape `(N, ndim)`
        Particle positions :math:`\\mathbf{r}_i`
        in 2D or 3D for :math:`N` particles.
        Passed to ``scipy.spatial.cKDTree``.
    boxsize : `list` of `float`
        The rectangular domain over which
        to apply periodic boundary conditions.
        Passed to ``scipy.spatial.cKDTree``.
    orientations : `np.ndarray`, shape `(N, ndim)`
        Particle orientation vectors :math:`\\mathbf{p}_i`.
        Vectors should be unitary, but they will be
        normalized automatically.
    rmin : `float`, optional
        Minimum :math:`r` value in :math:`g(r, \\phi, \\theta)`.
    rmax : `float`, optional
        Cutoff radius for KDTree search and
        maximum :math:`r` value in :math:`g(r, \\phi, \\theta)`.
        Default is half the maximum dimension of ``boxsize``.
    nr : `int`, optional
        Number of points to bin in :math:`r`.
    nphi : `int`, optional
        Number of points to bin in :math:`\\phi`
    ntheta : `int`, optional
        Number of points to bin in :math:`\\theta`
    bench : `bool`, optional
        Print message for time of calculation.
    Returns
    -------
    g : `np.ndarray`, shape `(nr, nphi, ntheta)`
        Radial distribution function :math:`g(r, \\phi, \\theta)`.
        If the user does not bin for a certain coordinate,
        ``g`` will not be 3 dimensional (e.g. if ``nphi = None``,
        ``g`` will be shape ``(nr, ntheta)``).
    r : `np.ndarray`, shape `(nr,)`
        Left edges of radial bins :math:`r`.
    phi : `np.ndarray`, shape `(nphi,)`
        Left edges of angular bins :math:`\\phi \\in [-\\pi, \\pi)`.
    theta : `np.ndarray`, shape `(ntheta,)`
        Left edges of angular bins :math:`\\theta \\in [0, \\pi)`.
        Not returned for 2D datasets.
    """
    N, ndim = positions.shape
    boxsize = np.array(boxsize)

    if ndim not in [2, 3]:
        raise ValueError("Dimension of space must be 2 or 3")

    if orientations is not None:
        if orientations.shape != (N, ndim):
            msg = f"Shape of orientations array must match positions array {(N, ndim)}"
            raise ValueError(msg)
    else:
        orientations = np.array([])

    # Binning keyword args
    rmin = 0 if rmin is None else rmin
    rmax = max(boxsize)/2 if rmax is None else rmax
    nphi = 1 if nphi is None else nphi
    ntheta = 1 if ntheta is None or ndim == 2 else ntheta

    # Periodic boundary conditions
    _impose_pbc(positions, boxsize)

    if bench:
        t0 = time()

    # Get particle pairs
    pairs = _get_pairs(positions, boxsize, rmax)

    if bench:
        t1 = time()
        print(f"Counted {len(pairs)} pairs: {t1-t0:.04f} s")

    # Get displacements
    r, phi, theta = _get_displacements(positions, orientations, pairs,
                                       boxsize, rmax, nr, nphi, ntheta)

    if bench:
        t2 = time()
        print(f"Displacement calculation: {t2-t1:.04f} s")

    # Get g(r, phi)
    r_n = np.linspace(rmin, rmax, nr+1)
    phi_m = 2*np.pi*np.linspace(0, 1, nphi+1) - np.pi
    theta_l = np.pi*np.linspace(0, 1, ntheta+1)
    g = _get_distribution(r, phi, theta, N, boxsize, r_n, phi_m, theta_l)

    del r, phi, theta

    out = [g, r_n[:-1], phi_m[:-1]]
    if ndim == 3:
        out.append(theta_l[:-1])

    return out


def _get_distribution(r, phi, theta, N, boxsize, r_n, phi_m, theta_l):
    '''Generate spatial distribution function'''
    # Prepare arguments
    samples, bins = [], []
    for s, b in [(r, r_n), (phi, phi_m), (theta, theta_l)]:
        if s.size > 1:
            samples.append(s)
            bins.append(b)
    # Bin
    count, edges = np.histogramdd(samples, bins=bins)
    # Scale with bin volume and density
    ndim = boxsize.size
    density = N/(np.prod(boxsize))
    vol = np.squeeze(_get_volume(count, r_n, phi_m, theta_l, ndim))
    g = count/(N*vol*density)
    return g


@nb.njit(parallel=True, cache=True)
def _get_volume(count, r, phi, theta, ndim):
    '''Get volume elements for (r, phi, theta) bins'''
    nr, nphi, ntheta = r.size-1, phi.size-1, theta.size-1
    vol = np.zeros((nr, nphi, ntheta))
    for n in nb.prange(nr):
        dr = (r[n+1]**ndim-r[n]**ndim) / ndim
        for m in range(nphi):
            dphi = phi[m+1] - phi[m]
            for l in range(ntheta):
                vol[n, m, l] = dphi * dr
                if ndim == 3:
                    vol[n, m, l] *= np.cos(theta[l]) - np.cos(theta[l+1])
    return vol


@nb.njit(parallel=True, cache=True)
def _get_displacements(r, p, pairs, boxsize, rmax, nr, nphi, ntheta):
    '''Get displacements between pairs'''
    rotate = True if p.shape == r.shape else False
    ndim = r.shape[-1]
    npairs = pairs.shape[0]
    rnorm = np.zeros(npairs) if nr > 1 else np.array([0.])
    phi = np.zeros(npairs) if nphi > 1 else np.array([0.])
    theta = np.zeros(npairs) if ntheta > 1 else np.array([0.])
    for index in nb.prange(npairs):
        pair = pairs[index]
        i, j = pair
        r_i, r_j = r[i], r[j]
        r_ij = r_j - r_i
        if np.linalg.norm(r_ij) >= rmax:
            # Fix periodic image
            image = _closest_image(r_i, r_j, boxsize)
            r_ij = image - r_i
        if rotate:
            # Rotate particle head to +z direction
            p_i = p[i] / np.linalg.norm(p[i])
            angle = np.arccos(p_i[-1])
            c, s = np.cos(angle), np.sin(angle)
            if ndim == 2:
                R = np.array(((c, -s), (s, c)))
            else:
                R = np.array(((c, -s, 0), (s, c, 0), (0, 0, 1)))
            r_ij = R @ r_ij
        norm = np.linalg.norm(r_ij)
        if nr > 1:
            rnorm[index] = norm
        if nphi > 1:
            phi[index] = np.arctan2(r_ij[1], r_ij[0])
        if ntheta > 1:
            theta[index] = np.arccos(r_ij[2] / norm)
    return rnorm, phi, theta


def _get_pairs(coords, boxsize, rmax):
    '''Get coordinate pairs within distance rmax'''
    tree = spatial.cKDTree(coords, boxsize=boxsize)
    # Get unique pairs (i<j)
    temp = tree.query_pairs(r=rmax, output_type="ndarray")
    # Get rest of the pairs (i>=j)
    npairs = len(temp)
    pairs = np.zeros(shape=(2*npairs, 2), dtype=np.int)
    pairs[:npairs, :] = temp
    pairs[npairs:, :] = temp[:, [1, 0]]
    del tree, temp
    return pairs


@nb.njit(cache=True)
def _impose_pbc(coords, boxsize):
    '''Impose periodic boundary conditions for KDTree'''
    dim = len(boxsize)
    for j in range(len(coords)):
        p = coords[j]
        for i in range(dim):
            while p[i] < 0:
                p[i] = p[i]+boxsize[i]
            while p[i] > boxsize[i]:
                p[i] = p[i]-boxsize[i]


@nb.njit(cache=True)
def _closest_point(target, positions):
    '''Get closest positions to target in 2D and 3D'''
    target = np.array(target)
    positions = np.array(positions)
    distance = []
    for p in positions:
        distance.append(np.linalg.norm(p-target))
    distance = np.array(distance)
    ind = np.argmin(distance)
    return positions[ind], ind


@nb.njit(cache=True)
def _closest_point1d(target, positions):
    '''Get closest positions to target in 1D'''
    distance = []
    for p in positions:
        distance.append(np.abs(p-target))
    distance = np.array(distance)
    ind = np.argmin(distance)
    return positions[ind], ind


@nb.njit(cache=True)
def _closest_image(target, source, boxsize):
    '''Get closest periodic image to target'''
    dim = target.shape[0]
    assert source.shape[0] == dim
    image = np.zeros(dim)
    for i in range(dim):
        pts = [source[i], source[i]-boxsize[i], source[i]+boxsize[i]]
        pos, ind = _closest_point1d(target[i], pts)
        image[i] = pos
    return image


if __name__ == "__main__":

    from matplotlib import pyplot as plt

    N = 3000
    boxsize = [100, 100, 100]
    pos = np.random.rand(N, 3)*100
    orient = np.random.rand(N, 3)
    rmax = 50

    g, r, phi, theta = sdf(pos, boxsize, rmax=rmax,
                           orientations=orient, bench=True,
                           nr=150, ntheta=100, nphi=None)

    print(g.mean(), g.shape)

    if g.ndim == 1:
        S, q = structure_factor(g, r, N, boxsize, qmin=0, qmax=100, dq=.5)
        fig, axes = plt.subplots(ncols=2)
        axes[0].plot(r, g)
        axes[0].set_xlabel("$r$")
        axes[0].set_ylabel("$g(r)$")
        axes[1].plot(q, S)
        axes[1].set_xlabel("$q$")
        axes[1].set_ylabel("$S(q)$")
        plt.show()
    else:
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        angle = theta
        rmesh, amesh = np.meshgrid(r, angle)
        im = ax.contourf(amesh, rmesh, g.T, np.linspace(.9, 1.1, 70), cmap="plasma")
        ax.set_xlim((angle.min(), angle.max()))
        fig.colorbar(im)
        plt.show()