# Deals with postprocessing on generated segmentation.

import functools
import numpy as np
import nibabel as nib
from scipy.ndimage.measurements import label
from scipy.ndimage.morphology import binary_fill_holes
from skimage.feature import peak_local_max


def nifti_capable(wrapped):
    """Decorator to make a given function compatible with input being Nifti objects.

    Args:
        wrapped: Given function.

    Returns:
        Functions' return.
    """
    @functools.wraps(wrapped)
    def wrapper(data, *args, **kwargs):
        if isinstance(data, nib.Nifti1Image):
            return nib.Nifti1Image(wrapper(np.copy(np.asanyarray(data.dataobj)), *args, **kwargs), data.affine)
        return wrapped(data, *args, **kwargs)

    return wrapper


def binarize_with_low_threshold(wrapped):
    """Decorator to set low values (< 0.001) to 0.

    Args:
        wrapped: Given function.

    Returns:
        Functions' return.
    """
    @functools.wraps(wrapped)
    def wrapper(data, *args, **kwargs):
        if not np.array_equal(data, data.astype(bool)):
            return mask_predictions(data, wrapper(threshold_predictions(data, thr=0.001), *args, **kwargs))
        return wrapped(data, *args, **kwargs)

    return wrapper


def multilabel_capable(wrapped):
    """Decorator to make a given function compatible multilabel images.

    Args:
        wrapped: Given function.

    Returns:
        Functions' return.
    """
    @functools.wraps(wrapped)
    def wrapper(data, *args, **kwargs):
        if len(data.shape) == 4:
            label_list = []
            for i in range(data.shape[-1]):
                out_data = wrapped(data[..., i], *args, **kwargs)
                label_list.append(out_data)
            return np.array(label_list).transpose((1, 2, 3, 0))
        return wrapped(data, *args, **kwargs)

    return wrapper


@nifti_capable
def threshold_predictions(predictions, thr=0.5):
    """Threshold a soft (i.e. not binary) array of predictions given a threshold value, and returns
    a binary array.

    Args:
        predictions (ndarray or nibabel object): Image to binarize.
        thr (float): Threshold value: voxels with a value < to thr are assigned 0 as value, 1
            otherwise.

    Returns:
        ndarray: ndarray or nibabel (same object as the input) containing only zeros or ones. Output type is int.
    """
    thresholded_preds = np.copy(predictions)[:]
    low_values_indices = thresholded_preds < thr
    thresholded_preds[low_values_indices] = 0
    low_values_indices = thresholded_preds >= thr
    thresholded_preds[low_values_indices] = 1
    return thresholded_preds.astype(np.int)


@nifti_capable
@binarize_with_low_threshold
def keep_largest_object(predictions):
    """Keep the largest connected object from the input array (2D or 3D).

    Args:
        predictions (ndarray or nibabel object): Input segmentation. Image could be 2D or 3D.

    Returns:
        ndarray or nibabel (same object as the input).
    """
    # Find number of closed objects using skimage "label"
    labeled_obj, num_obj = label(np.copy(predictions))
    # If more than one object is found, keep the largest one
    if num_obj > 1:
        # Keep the largest object
        predictions[np.where(labeled_obj != (np.bincount(labeled_obj.flat)[1:].argmax() + 1))] = 0
    return predictions


@nifti_capable
def keep_largest_object_per_slice(predictions, axis=2):
    """Keep the largest connected object for each 2D slice, along a specified axis.

    Args:
        predictions (ndarray or nibabel object): Input segmentation. Image could be 2D or 3D.
        axis (int): 2D slices are extracted along this axis.

    Returns:
        ndarray or nibabel (same object as the input).
    """
    # Split the 3D input array as a list of slice along axis
    list_preds_in = np.split(predictions, predictions.shape[axis], axis=axis)
    # Init list of processed slices
    list_preds_out = []
    # Loop across the slices along the given axis
    for idx in range(len(list_preds_in)):
        slice_processed = keep_largest_object(np.squeeze(list_preds_in[idx], axis=axis))
        list_preds_out.append(slice_processed)
    return np.stack(list_preds_out, axis=axis)


@nifti_capable
@multilabel_capable
def fill_holes(predictions, structure=(3, 3, 3)):
    """Fill holes in the predictions using a given structuring element.
    Note: This function only works for binary segmentation.

    Args:
        predictions (ndarray or nibabel object): Input binary segmentation. Image could be 2D or 3D.
        structure (tuple of integers): Structuring element, number of ints equals
            number of dimensions in the input array.

    Returns:
        ndrray or nibabel (same object as the input). Output type is int.
    """
    assert np.array_equal(predictions, predictions.astype(bool))
    assert len(structure) == len(predictions.shape)
    return binary_fill_holes(predictions, structure=np.ones(structure)).astype(np.int)


@nifti_capable
def mask_predictions(predictions, mask_binary):
    """Mask predictions using a binary mask: sets everything outside the mask to zero.

    Args:
        predictions (ndarray or nibabel object): Input binary segmentation. Image could be 2D or 3D.
        mask_binary (ndarray): Numpy array with the same shape as predictions, containing only zeros or ones.

    Returns:
        ndarray or nibabel (same object as the input).
    """
    assert predictions.shape == mask_binary.shape
    assert np.array_equal(mask_binary, mask_binary.astype(bool))
    return predictions * mask_binary


def coordinate_from_heatmap(nifti_image, thresh=0.3):
    """
    Retrieve coordinates of local maxima in a soft segmentation.
    Args:
        nifti_image (nibabel object): nifti image of the soft segmentation.
        thresh (float): Relative threshold for local maxima, i.e., after normalizing
        the min and max between 0 and 1, respectively.

    Returns:
        list: A list of computed coordinates found by local maximum. each element will be a list composed of
        [x, y, z]
    """

    image = np.array(nifti_image.dataobj)
    coordinates_tmp = peak_local_max(image, min_distance=5, threshold_rel=thresh)
    return coordinates_tmp


def label_file_from_coordinates(nifti_image, coord_list):
    """
    Creates a nifti object with single-voxel labels. Each label has a value of 1. The nifti object as the same
    orientation as the input.
    Args:
        nifti_image (nibabel object): Path to the image which affine matrix will be used to generate a new image with
        labels.
        coord_list (list): list of coordinates. Each element is [x, y, z]. Orientation should be the same as the image

    Returns:
        nib_pred: A nifti object containing the singe-voxel label of value 1. The matrix will be the same size as
        `nifti_image`.

    """

    imsh = list(np.array(nifti_image.dataobj).shape)
    # create an empty 3d object.
    label_array = np.zeros(tuple(imsh))

    for j in range(len(coord_list)):
        label_array[coord_list[j][0], coord_list[j][1], coord_list[j][2]] = 1

    nib_pred = nib.Nifti1Image(label_array, nifti_image.affine)

    return nib_pred
