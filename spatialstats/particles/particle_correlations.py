"""
Routines to calculate 2-point correlation functions
:math:`G(\\mathbf{r}), \ S(\\mathbf{q})` for point and
rod-like particle pairs.
Can reduce to the usual isotropic :math:`G(r)` with the
corresponding fourier representation :math:`S(q)`.

See `here <https://en.wikipedia.org/wiki/Radial_distribution_function>`_
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


def fourier_corr(gr, r, N, boxsize, q=None, **kwargs):
    """
    Calculate the isotropic fourier correlation function :math:`S(q)` from
    the pair correlation function :math:`G(r)` of a set of :math:`N`
    particle positions in a 2D or 3D periodic box with volume :math:`V`.

    The fourier-space pairwise correlation function in 2D and 3D are fourier
    transforms of :math:`G(r)`, simplified to

    .. math::

        S(q) = 1 + 4\\pi \\rho \int dr \ r^2 \ j_0(qr) G(r)

    and

    .. math::

        S(q) = 1 + 2\\pi \\rho \int dr \ r \ J_{0}(qr) G(r),

    where :math:`\\rho = N/V` and :math:`J_{0}, \ j_{0}` are the 0th
    order bessel function and spherical bessel functions, respectively.

    If finding the structure factor for the radial distribution function
    :math:`g(r)`, conventionally :math:`S` is computed by setting
    :math:`G(r) = g(r) - 1` because :math:`g` decays to 1.

    Parameters
    ----------
    gr : `np.ndarray`
        The pairwise correlation function :math:`G(r)` from
        :ref:`spatialstats.particles.corr<corr>`.
    r : `np.ndarray`
        The domain of :math:`G(r)` from
        :ref:`spatialstats.particles.corr<corr>`.
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
        The fourier 2-point correlation function :math:`S(q)`.
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
        '''Integrand for isotropic correlation function'''
        rho = N/np.prod(boxsize)
        g = gr-1 if spatial else gr
        if ndim == 3:
            f = np.sin(q*r)*r*g
            return 1+4*np.pi*rho*simps(f, r)/q
        else:
            f = jv(0, q*r)*r*g
            return 1+2*np.pi*rho*simps(f, r)

    # Integrate for all q
    Sq = []
    for j in range(len(q)):
        Sq.append(S(q[j]))
    Sq = np.array(Sq)

    return Sq, q


def corr(positions, boxsize, weights=None, z=1, orientations=None, rmin=None, rmax=None,
         nr=100, nphi=None, ntheta=None, int=np.int32, float=np.float64,
         bench=False, **kwargs):
    """
    .. _corr:

    Compute the 2-point correlaton function
    :math:`G(\\mathbf{r})` for a set of :math:`N`
    point-like or rod-like particles
    :math:`\\mathbf{r}_i` in a 2D or 3D periodic box, where
    :math:`\\mathbf{r} = (r, \\phi, \\theta)` are the spherical
    coordinates for displacement vectors between particle pairs
    :math:`\\mathbf{r} = \\mathbf{r}_i - \\mathbf{r}_j`.
    :math:`\\phi` is the azimuthal angle and :math:`\\theta` is
    the inclination angle.

    If ``weight = None``, :math:`G(\\mathbf{r} = g(\\mathbf{r})`,
    i.e. the spatial distribution function. This is computed as
    :math:`g(\\mathbf{r}) = \\langle \\delta(\\mathbf{r}_j - \\mathbf{r}_i) \\rangle`,
    where :math:`\\langle ... \\rangle is an average over particle pair displacements
    :math:`\\mathbf{r}_j - \\mathbf{r}_i` in a periodic box for each origin
    :math:`\\mathbf{r}_i`.

    Generally, if the ``weights`` argument is a vector defined for all
    particles :math:`\\mathbf{w}_i`, the pair correlation
    function is computed as
    :math:`G(\\mathbf{r}) = \\langle (\\mathbf{w}_i \\cdot \\mathbf{w}_j)^z \\rangle`,
    where :math:`z` is some exponent.

    If particles orientations :math:`\\mathbf{p}_i` are included,
    define :math:`(r, \\phi, \\theta)` as the rotated
    coordinate system with :math:`\\mathbf{p}_i` pointed in the
    :math:`+z` direction.

    .. note::
        Reduces to the 1D radial distribution function :math:`g(r)`
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
    weights : `np.ndarray`, shape `(N, ndim)`, optional
        Particle vectors :math:`\\mathbf{w}_i` over which
        to calculate pair correlation function.
    z : `int`
        Exponent in averaging
        :math:`\\langle (\\mathbf{w}_i \\cdot \\mathbf{w}_j)^z \\rangle`.
    orientations : `np.ndarray`, shape `(N, ndim)`, optional
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
        Number of points to bin in :math:`\\phi`.
    ntheta : `int`, optional
        Number of points to bin in :math:`\\theta`.
    int : `np.dtype`, optional
        Integer type for pair counting array.
        Lets the user relax memory requirements.
    float : `np.dtype`, optional
        Floating-point type for displacement buffers.
        Lets the user relax memory requirements.
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
            msg = f"Shape of orientations must match positions array {(N, ndim)}"
            raise ValueError(msg)
    else:
        orientations = np.zeros((1, ndim), dtype=float)
    if weights is not None:
        if weights.shape != (N, ndim):
            msg = f"Shape of weights must match positions array {(N, ndim)}"
            raise ValueError(msg)
    else:
        weights = np.zeros((1, ndim), float)

    # Binning keyword args
    rmin = 0 if rmin is None else rmin
    rmax = max(boxsize)/2 if rmax is None else rmax
    nr = 1 if nr is None or nr < 1 else nr
    nphi = 1 if nphi is None or nphi < 1 else nphi
    ntheta = 1 if ntheta is None or ntheta < 1 or ndim == 2 else ntheta
    ncoords = 0
    for n in [nr, nphi, ntheta]:
        if n > 1:
            ncoords += 1

    # Periodic boundary conditions
    _impose_pbc(positions, boxsize)

    if bench:
        t0 = time()

    # Get particle pairs
    pairs = _get_pairs(positions, boxsize, rmax, int)
    npairs = len(pairs)

    if npairs == 0:
        raise ValueError(f"Counted 0 pairs. Try increasing rmax")

    if bench:
        t1 = time()
        print(f"Counted {npairs} pairs: {t1-t0:.04f} s")

    # Get displacements
    args = (positions, weights, z, orientations, boxsize, rmax, nr, nphi, ntheta)
    rbuff = np.zeros((2*npairs, ncoords), dtype=float)
    wbuff = np.zeros((2*npairs), dtype=float) if weights.shape[0] > 1 else np.zeros([0])
    rij, wiwj = _get_displacements(rbuff, wbuff, pairs, *args)

    # Get correlation function
    r_n = np.linspace(rmin, rmax, nr+1)
    phi_m = 2*np.pi*np.linspace(0, 1, nphi+1) - np.pi
    theta_l = np.pi*np.linspace(0, 1, ntheta+1)
    g = _get_distribution(rij, wiwj, N, boxsize, r_n, phi_m, theta_l, **kwargs)

    if bench:
        t2 = time()
        print(f"Displacement calculation: {t2-t1:.04f} s")

    del rij, wiwj, rbuff, pairs

    out = [g, r_n[:-1], phi_m[:-1]]
    if ndim == 3:
        out.append(theta_l[:-1])

    return tuple(out)


def _get_distribution(rij, wiwj, N, boxsize, r_n, phi_m, theta_l, **kwargs):
    '''Generate pair correlation function'''
    # Prepare arguments
    bins = []
    for b in [r_n, phi_m, theta_l]:
        if b.size > 2:
            bins.append(b)
    # Bin
    weights = wiwj if wiwj.size > 1 else None
    count, edges = np.histogramdd(rij, bins=bins, weights=weights, **kwargs)
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
def _get_displacements(rbuff, wbuff, pairs, r, w, z, p, boxsize, rmax, nr, nphi, ntheta):
    '''Get displacements between pairs and correlation weights'''
    rotate = True if p.shape == r.shape else False
    nthreads = pairs.shape[0]
    for idx1 in nb.prange(nthreads):
        for idx2 in range(2):
            pair = pairs[idx1]
            index = idx1 + nthreads*idx2
            i, j = pair if idx2 == 0 else pair[::-1]
            # Get displacement vector
            r_i, r_j = r[i], r[j]
            r_ij = r_j - r_i
            if _norm(r_ij) >= rmax:
                # Fix periodic image
                image = _closest_image(r_i, r_j, boxsize)
                r_ij = image - r_i
            if rotate:
                # Rotate particle head to +z direction
                p_i = p[i] / _norm(p[i])
                R = _rotation_matrix(p_i)
                r_ij = _matvec(R, r_ij)
            # Fill buffers
            if wbuff.size > 1:
                wbuff[index] = _dot(w[i], w[j])**z
            k = 0
            norm = _norm(r_ij)
            if nr > 1:
                rbuff[index, k] = norm
                k += 1
            if nphi > 1:
                rbuff[index, k] = np.arctan2(r_ij[1], r_ij[0])
                k += 1
            if ntheta > 1:
                rbuff[index, k] = np.arccos(r_ij[2] / norm)
    return rbuff, wbuff


@nb.njit(cache=True)
def _rotation_matrix(p):
    '''
    Rotation matrix to align coords so that
    a vector p is in the +z direction.
    In 3D, use the Rodrigues rotation formula.
    '''
    # Angle of rotation is arccos(p . z)
    cos, sin = p[-1], np.sin(np.arccos(p[-1]))
    if p.size == 2:
        R = np.array(((cos, -sin), (sin, cos)))
    else:
        # Rotation axis k = p x z
        k = np.array([p[1], -p[0], 0])
        k /= _norm(k)
        # Cross product matrix K
        K = np.array(((0, -k[2], k[1]),
                      (k[2], 0, -k[0]),
                      (-k[1], k[0], 0)))
        # Matrix formulation of Rodrigues formula
        R = np.eye(3) + sin*K + (1-cos)*_matmul(K, K)
    return R


def _get_pairs(coords, boxsize, rmax, int):
    '''Get coordinate pairs within distance rmax'''
    tree = spatial.cKDTree(coords, boxsize=boxsize)
    # Get unique pairs (i<j)
    pairs = tree.query_pairs(r=rmax)
    return np.array(list(pairs), dtype=int)


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
        distance.append(_norm(p-target))
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


@nb.njit(cache=True)
def _norm(x):
    return np.sqrt(_dot(x, x))


@nb.njit(cache=True)
def _dot(a, b):
    dot = 0
    n = a.size
    for i in range(n):
        dot += a[i]*b[i]
    return dot


@nb.njit(cache=True)
def _matvec(A, x):
    b = np.zeros_like(x)
    m, n = A.shape
    for i in range(m):
        b[i] = _dot(A[i, :], x[:])
    return b


@nb.njit(cache=True)
def _matmul(A, B):
    C = np.zeros_like(A)
    m, n = A.shape
    for i in range(m):
        for j in range(n):
            C[i, j] = _dot(A[i, :], B[:, j])
    return C



if __name__ == "__main__":

    from matplotlib import pyplot as plt

    N = 200
    boxsize = [10, 10, 10]
    np.random.seed(1234)
    pos = np.random.rand(N, 3)*100
    #orient = np.ones((N, 3))
    weights = np.random.rand(N, 3)*2 - 1
    rmax = 5
    orient = None
    #weights = None

    g, r, phi, theta = corr(pos, boxsize, rmax=rmax,
                            orientations=orient, z=2,
                            weights=weights, bench=True,
                            nr=150, ntheta=10)

    print(g.mean(), g.shape)

    if g.ndim == 1:
        f = g-g.mean()
        S, q = fourier_corr(f, r, N, boxsize)
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
        im = ax.contourf(amesh, rmesh, g.T, 100, cmap="plasma")
        ax.set_xlim((angle.min(), angle.max()))
        fig.colorbar(im)
        plt.show()