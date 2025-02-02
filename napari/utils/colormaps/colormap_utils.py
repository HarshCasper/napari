import os
from threading import Lock
from typing import Dict, List, Tuple, Union

import numpy as np
from vispy.color import BaseColormap as VispyColormap
from vispy.color import get_colormap, get_colormaps

from .bop_colors import bopd
from .colormap import Colormap
from .vendored import cm, colorconv

_matplotlib_list_file = os.path.join(
    os.path.dirname(__file__), 'matplotlib_cmaps.txt'
)
with open(_matplotlib_list_file) as fin:
    matplotlib_colormaps = [line.rstrip() for line in fin]


ValidColormapArg = Union[
    str,
    VispyColormap,
    Colormap,
    Tuple[str, VispyColormap],
    Tuple[str, Colormap],
    Dict[str, VispyColormap],
    Dict[str, Colormap],
    Dict,
]


primary_color_names = ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow']
primary_colors = np.array(
    [(1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 0)],
    dtype=float,
)


SIMPLE_COLORMAPS = {
    name: Colormap(name=name, colors=[[0.0, 0.0, 0.0], color])
    for name, color in zip(primary_color_names, primary_colors)
}

# dictionay for bop colormap objects
BOP_COLORMAPS = {k: Colormap(v, name=k) for k, v in bopd.items()}


def _all_rgb():
    """Return all 256**3 valid rgb tuples."""
    base = np.arange(256, dtype=np.uint8)
    r, g, b = np.meshgrid(base, base, base, indexing='ij')
    return np.stack((r, g, b), axis=-1).reshape((-1, 3))


# obtained with colorconv.rgb2luv(_all_rgb().reshape((-1, 256, 3)))
LUVMIN = np.array([0.0, -83.07790815, -134.09790293])
LUVMAX = np.array([100.0, 175.01447356, 107.39905336])
LUVRNG = LUVMAX - LUVMIN

# obtained with colorconv.rgb2lab(_all_rgb().reshape((-1, 256, 3)))
LABMIN = np.array([0.0, -86.18302974, -107.85730021])
LABMAX = np.array([100.0, 98.23305386, 94.47812228])
LABRNG = LABMAX - LABMIN


def convert_vispy_colormap(colormap, name='vispy'):
    """Convert a vispy colormap object to a napari colormap.

    Parameters
    ----------
    colormap : vispy.color.Colormap
        Vispy colormap object that should be converted.
    name : str
        Name of colormap, optional.

    Returns
    -------
    napari.utils.Colormap
    """
    if not isinstance(colormap, VispyColormap):
        raise TypeError(
            'Colormap must be a vispy colormap ' 'if passed to from_vispy'
        )

    # Not all vispy colormaps have an `_controls`
    # but if they do, we want to use it
    if hasattr(colormap, '_controls'):
        controls = colormap._controls
    else:
        controls = np.zeros((0,))

    # Not all vispy colormaps have an `interpolation`
    # but if they do, we want to use it
    if hasattr(colormap, 'interpolation'):
        interpolation = colormap.interpolation
    else:
        interpolation = 'linear'

    return Colormap(
        name=name,
        colors=colormap.colors.rgba,
        controls=controls,
        interpolation=interpolation,
    )


def _validate_rgb(colors, *, tolerance=0.0):
    """Return the subset of colors that is in [0, 1] for all channels.

    Parameters
    ----------
    colors : array of float, shape (N, 3)
        Input colors in RGB space.

    Returns
    -------
    filtered_colors : array of float, shape (M, 3), M <= N
        The subset of colors that are in valid RGB space.

    Other Parameters
    ----------------
    tolerance : float, optional
        Values outside of the range by less than ``tolerance`` are allowed and
        clipped to be within the range.

    Examples
    --------
    >>> colors = np.array([[  0. , 1.,  1.  ],
    ...                    [  1.1, 0., -0.03],
    ...                    [  1.2, 1.,  0.5 ]])
    >>> _validate_rgb(colors)
    array([[0., 1., 1.]])
    >>> _validate_rgb(colors, tolerance=0.15)
    array([[0., 1., 1.],
           [1., 0., 0.]])
    """
    lo = 0 - tolerance
    hi = 1 + tolerance
    valid = np.all((colors > lo) & (colors < hi), axis=1)
    filtered_colors = np.clip(colors[valid], 0, 1)
    return filtered_colors


def low_discrepancy_image(image, seed=0.5, margin=1 / 256):
    """Generate a 1d low discrepancy sequence of coordinates.

    Parameters
    ----------
    image : array of int
        A set of labels or label image.
    seed : float
        The seed from which to start the quasirandom sequence.
    margin : float
        Values too close to 0 or 1 will get mapped to the edge of the colormap,
        so we need to offset to a margin slightly inside those values. Since
        the bin size is 1/256 by default, we offset by that amount.

    Returns
    -------
    image_out : array of float
        The set of ``labels`` remapped to [0, 1] quasirandomly.

    """
    phi_mod = 0.6180339887498948482
    image_float = seed + image * phi_mod
    # We now map the floats to the range [0 + margin, 1 - margin]
    image_out = margin + (1 - 2 * margin) * (
        image_float - np.floor(image_float)
    )
    return image_out


def color_dict_to_colormap(colors):
    """
    Generate a color map based on the given color dictionary

    Parameters
    ----------
    colors : dict of int to array of float, shape (4)
        Mapping between labels and color

    Returns
    -------
    colormap : napari.utils.Colormap
        Colormap constructed with provided control colors
    label_color_index : dict of int
        Mapping of Label to color control point within colormap
    """

    control_colors = np.unique(list(colors.values()), axis=0)
    colormap = Colormap(control_colors)
    control2index = {
        tuple(ctrl): i / (len(control_colors) - 1)
        for i, ctrl in enumerate(control_colors)
    }
    label_color_index = {
        label: control2index[tuple(color)] for label, color in colors.items()
    }

    return colormap, label_color_index


def _low_discrepancy(dim, n, seed=0.5):
    """Generate a 1d, 2d, or 3d low discrepancy sequence of coordinates.

    Parameters
    ----------
    dim : one of {1, 2, 3}
        The dimensionality of the sequence.
    n : int
        How many points to generate.
    seed : float or array of float, shape (dim,)
        The seed from which to start the quasirandom sequence.

    Returns
    -------
    pts : array of float, shape (n, dim)
        The sampled points.

    References
    ----------
    ..[1]: http://extremelearning.com.au/unreasonable-effectiveness-of-quasirandom-sequences/  # noqa: E501
    """
    phi1 = 1.6180339887498948482
    phi2 = 1.32471795724474602596
    phi3 = 1.22074408460575947536
    seed = np.broadcast_to(seed, (1, dim))
    phi = np.array([phi1, phi2, phi3])
    g = 1 / phi
    n = np.reshape(np.arange(n), (n, 1))
    pts = (seed + (n * g[:dim])) % 1
    return pts


def _color_random(n, *, colorspace='lab', tolerance=0.0, seed=0.5):
    """Generate n random RGB colors uniformly from LAB or LUV space.

    Parameters
    ----------
    n : int
        Number of colors to generate.
    colorspace : str, one of {'lab', 'luv', 'rgb'}
        The colorspace from which to get random colors.
    tolerance : float
        How much margin to allow for out-of-range RGB values (these are
        clipped to be in-range).
    seed : float or array of float, shape (3,)
        Value from which to start the quasirandom sequence.

    Returns
    -------
    rgb : array of float, shape (n, 3)
        RGB colors chosen uniformly at random from given colorspace.
    """
    factor = 6  # about 1/5 of random LUV tuples are inside the space
    expand_factor = 2
    rgb = np.zeros((0, 3))
    while len(rgb) < n:
        random = _low_discrepancy(3, n * factor, seed=seed)
        if colorspace == 'luv':
            raw_rgb = colorconv.luv2rgb(random * LUVRNG + LUVMIN)
        elif colorspace == 'rgb':
            raw_rgb = random
        else:  # 'lab' by default
            raw_rgb = colorconv.lab2rgb(random * LABRNG + LABMIN)
        rgb = _validate_rgb(raw_rgb, tolerance=tolerance)
        factor *= expand_factor
    return rgb[:n]


def label_colormap(num_colors=256, seed=0.5):
    """Produce a colormap suitable for use with a given label set.

    Parameters
    ----------
    num_colors : int, optional
        Number of unique colors to use. Default used if not given.
    seed : float or array of float, length 3
        The seed for the random color generator.

    Returns
    -------
    colormap : napari.utils.Colormap
        A colormap for use with labels are remapped to [0, 1].

    Notes
    -----
    0 always maps to fully transparent.
    """
    # Starting the control points slightly above 0 and below 1 is necessary
    # to ensure that the background pixel 0 is transparent
    midpoints = np.linspace(0.00001, 1 - 0.00001, num_colors - 1)
    control_points = np.concatenate(([0], midpoints, [1.0]))
    # make sure to add an alpha channel to the colors
    colors = np.concatenate(
        (_color_random(num_colors, seed=seed), np.full((num_colors, 1), 1)),
        axis=1,
    )
    colors[0, :] = 0  # ensure alpha is 0 for label 0
    return Colormap(
        name='label_colormap',
        colors=colors,
        controls=control_points,
        interpolation='zero',
    )


def vispy_or_mpl_colormap(name):
    """Try to get a colormap from vispy, or convert an mpl one to vispy format.

    Parameters
    ----------
    name : str
        The name of the colormap.

    Returns
    -------
    colormap : napari.utils.Colormap
        The found colormap.

    Raises
    ------
    KeyError
        If no colormap with that name is found within vispy or matplotlib.
    """
    vispy_cmaps = get_colormaps()
    if name in vispy_cmaps:
        cmap = get_colormap(name)
        colormap = convert_vispy_colormap(cmap, name=name)
    else:
        try:
            mpl_cmap = getattr(cm, name)
        except AttributeError:
            raise KeyError(
                f'Colormap "{name}" not found in either vispy '
                'or matplotlib.'
            )
        mpl_colors = mpl_cmap(np.linspace(0, 1, 256))
        colormap = Colormap(name=name, colors=mpl_colors)
    return colormap


# A dictionary mapping names to VisPy colormap objects
ALL_COLORMAPS = {k: vispy_or_mpl_colormap(k) for k in matplotlib_colormaps}
ALL_COLORMAPS.update(SIMPLE_COLORMAPS)
ALL_COLORMAPS.update(BOP_COLORMAPS)

# ... sorted alphabetically by name
AVAILABLE_COLORMAPS = dict(sorted(ALL_COLORMAPS.items()))
# lock to allow update of AVAILABLE_COLORMAPS in threads
AVAILABLE_COLORMAPS_LOCK = Lock()

# curated colormap sets
# these are selected to look good or at least reasonable when using additive
# blending of multiple channels.
MAGENTA_GREEN = ['magenta', 'green']
RGB = ['red', 'green', 'blue']
CYMRGB = ['cyan', 'yellow', 'magenta', 'red', 'green', 'blue']


def increment_unnamed_colormap(
    existing: List[str], name: str = '[unnamed colormap]'
) -> str:
    """Increment name for unnamed colormap.

    Parameters
    ----------
    existing : list of str
        Names of existing colormaps.
    name : str, optional
        Name of colormap to be incremented. by default '[unnamed colormap]'

    Returns
    -------
    name : str
        Name of colormap after incrementing.
    """
    if name == '[unnamed colormap]':
        past_names = [n for n in existing if n.startswith('[unnamed colormap')]
        name = f'[unnamed colormap {len(past_names)}]'
    return name


def ensure_colormap(colormap: ValidColormapArg) -> Colormap:
    """Accept any valid colormap arg, and return (name, Colormap), or raise.

    Adds any new colormaps to AVAILABLE_COLORMAPS in the process.

    Parameters
    ----------
    colormap : ValidColormapArg
        colormap as str, napari.utils.Colormap.

    Returns
    -------
    Tuple[str, Colormap]
        Normalized name and napari.utils.Colormap.

    Raises
    ------
    KeyError
        If a string is provided that is not in AVAILABLE_COLORMAPS
    TypeError
        If a tuple is provided and the first element is not a string or the
        second element is not a Colormap.
    TypeError
        If a dict is provided and any of the values are not Colormap instances
        or valid inputs to the Colormap constructor.
    TypeError
        If ``colormap`` is not a ``str``, ``dict``, ``tuple``, or ``Colormap``
    """
    with AVAILABLE_COLORMAPS_LOCK:
        if isinstance(colormap, str):
            name = colormap
            if name not in AVAILABLE_COLORMAPS:
                cmap = vispy_or_mpl_colormap(
                    name
                )  # raises KeyError if not found
                AVAILABLE_COLORMAPS[name] = cmap
        elif isinstance(colormap, Colormap):
            AVAILABLE_COLORMAPS[colormap.name] = colormap
            name = colormap.name
        elif isinstance(colormap, VispyColormap):
            # if a vispy colormap instance is provided, make sure we don't already
            # know about it before adding a new unnamed colormap
            name = None
            for key, val in AVAILABLE_COLORMAPS.items():
                if colormap == val:
                    name = key
                    break
            if not name:
                name = increment_unnamed_colormap(AVAILABLE_COLORMAPS)
            # Convert from vispy colormap
            cmap = convert_vispy_colormap(colormap, name=name)
            AVAILABLE_COLORMAPS[name] = cmap

        elif isinstance(colormap, tuple):
            if not (
                len(colormap) == 2
                and (
                    isinstance(colormap[1], VispyColormap)
                    or isinstance(colormap[1], Colormap)
                )
                and isinstance(colormap[0], str)
            ):
                raise TypeError(
                    "When providing a tuple as a colormap argument, the first "
                    "element must be a string and the second a Colormap instance"
                )
            name, cmap = colormap
            # Convert from vispy colormap
            if isinstance(cmap, VispyColormap):
                cmap = convert_vispy_colormap(cmap, name=name)
            else:
                cmap.name = name
            AVAILABLE_COLORMAPS[name] = cmap

        elif isinstance(colormap, dict):
            if 'colors' in colormap and not (
                isinstance(colormap['colors'], VispyColormap)
                or isinstance(colormap['colors'], Colormap)
            ):
                cmap = Colormap(**colormap)
                name = cmap.name
                AVAILABLE_COLORMAPS[name] = cmap
            elif not all(
                (isinstance(i, VispyColormap) or isinstance(i, Colormap))
                for i in colormap.values()
            ):
                raise TypeError(
                    "When providing a dict as a colormap, "
                    "all values must be Colormap instances"
                )
            else:
                # Convert from vispy colormaps
                for key, cmap in colormap.items():
                    # Convert from vispy colormap
                    if isinstance(cmap, VispyColormap):
                        cmap = convert_vispy_colormap(cmap, name=key)
                    else:
                        cmap.name = key
                    name = key
                    colormap[name] = cmap
                AVAILABLE_COLORMAPS.update(colormap)
                if len(colormap) == 1:
                    name = list(colormap)[0]  # first key in dict
                elif len(colormap) > 1:
                    name = list(colormap.keys())[0]
                    import warnings

                    warnings.warn(
                        "only the first item in a colormap dict is used as an argument"
                    )
                else:
                    raise ValueError(
                        "Received an empty dict as a colormap argument."
                    )
        else:
            raise TypeError(
                f'invalid type for colormap: {type(colormap)}. '
                'Must be a {str, tuple, dict, napari.utils.Colormap, '
                'vispy.colors.Colormap}'
            )

    return AVAILABLE_COLORMAPS[name]


def make_default_color_array():
    return np.array([0, 0, 0, 1])
