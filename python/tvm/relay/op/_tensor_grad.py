# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#pylint: disable=invalid-name, unused-argument
"""Backend compiler related feature registration"""
from __future__ import absolute_import
from topi.util import get_const_tuple
from topi.nn.util import get_pad_tuple
from ..expr import const, Tuple, TupleGetItem
from .op import register_gradient
from .reduce import sum as _sum
from .transform import collapse_sum_like, broadcast_to_like, where, transpose, reshape, tile, \
        strided_slice
from .tensor import exp, negative, power, less, cos, sin
from .tensor import zeros_like, ones_like
from . import nn as _nn


@register_gradient("log")
def log_grad(orig, grad):
    """Returns [grad * (1 / x)]"""
    x = orig.args[0]
    return [grad * ones_like(x) / x]

@register_gradient("cos")
def cos_grad(orig, grad):
    """Returns [grad * (-sin(x))]"""
    x = orig.args[0]
    ones = ones_like(x)
    return [grad * (-ones * sin(x))]

@register_gradient("sin")
def sin_grad(orig, grad):
    """Returns [grad * cos(x)]"""
    x = orig.args[0]
    return [grad * cos(x)]

@register_gradient("exp")
def exp_grad(orig, grad):
    """Returns [grad * exp(x)]"""
    return [grad * exp(orig.args[0])]


@register_gradient("sqrt")
def sqrt_grad(orig, grad):
    """Returns [grad * 0.5 * (x ^ -0.5)]"""
    a = const(0.5)  # (TODO) type?
    return [grad * a * power(orig.args[0], negative(a))]


@register_gradient("sigmoid")
def sigmoid_grad(orig, grad):
    """Returns [grad * sigmoid(x) * (1 - sigmoid(x))]."""
    return [grad * orig * (ones_like(orig) - orig)]


@register_gradient("tanh")
def tanh_grad(orig, grad):
    """Returns grad * (1 - tanh(x) * tanh(x))."""
    return [grad * ones_like(orig) - orig * orig]


@register_gradient("nn.relu")
def relu_grad(orig, grad):
    """Returns grad * (select(x < 0, 0, 1))."""
    x = orig.args[0]
    zeros = zeros_like(x)
    ones = ones_like(x)
    return [where(less(x, zeros), zeros, ones * grad)]


@register_gradient("add")
def add_grad(orig, grad):
    """Returns [grad, grad]"""
    return [collapse_sum_like(grad, orig.args[0]),
            collapse_sum_like(grad, orig.args[1])]


@register_gradient("subtract")
def subtract_grad(orig, grad):
    """Returns [grad, -grad]"""
    return [collapse_sum_like(grad, orig.args[0]),
            collapse_sum_like(negative(grad), orig.args[1])]


@register_gradient("multiply")
def multiply_grad(orig, grad):
    """Returns [grad * y, grad * x]"""
    x, y = orig.args
    return [collapse_sum_like(grad * y, x),
            collapse_sum_like(grad * x, y)]


@register_gradient("divide")
def divide_grad(orig, grad):
    """Returns [grad / y,  - grad * (x / y) / y]"""
    x, y = orig.args
    return [collapse_sum_like(grad / y, x),
            collapse_sum_like(- (grad * orig / y), y)]


@register_gradient("zeros")
def zeros_grad(orig, grad):
    """Returns []"""
    return []


@register_gradient("ones")
def ones_grad(orig, grad):
    """Returns []"""
    return []


@register_gradient("zeros_like")
def zeros_like_grad(orig, grad):
    """Returns [0]"""
    return [orig]


@register_gradient("ones_like")
def ones_like_grad(orig, grad):
    """Returns [0]"""
    return [zeros_like(orig.args[0])]


@register_gradient("collapse_sum_like")
def collapse_sum_like_grad(orig, grad):
    """Returns [broadcast_to_like(grad, x), 0]"""
    x, y = orig.args
    return [broadcast_to_like(grad, x), zeros_like(y)]


@register_gradient("abs")
def abs_grad(orig, grad):
    """Returns grad * (select(x < 0, -1, 1))."""
    x = orig.args[0]
    zeros = zeros_like(x)
    ones = ones_like(x)
    return [where(less(x, zeros), -ones * grad, ones * grad)]


@register_gradient("clip")
def clip_grad(orig, grad):
    """Returns grad * (select(x < min || max < x , 0, 1))."""
    x = orig.args[0]
    a_min = orig.attrs.get_int("a_min")
    a_max = orig.attrs.get_int("a_max")
    a_mins = broadcast_to_like(const(a_min), x)
    a_maxs = broadcast_to_like(const(a_max), x)
    zeros = zeros_like(x)
    ones = ones_like(x)
    return [where(less(x, a_mins), zeros, where(less(a_maxs, x), zeros, ones * grad))]

@register_gradient("nn.max_pool2d")
def max_pool2d_grad(orig, grad):
    attrs = orig.attrs
    pool_grad = _nn.max_pool2d_grad(grad, orig.args[0], pool_size=attrs.pool_size,
                                    strides=attrs.strides, padding=attrs.padding,
                                    layout=attrs.layout, ceil_mode=attrs.ceil_mode)
    return [pool_grad]

@register_gradient("nn.avg_pool2d")
def avg_pool2d_grad(orig, grad):
    attrs = orig.attrs
    pool_grad = _nn.avg_pool2d_grad(grad, orig.args[0], pool_size=attrs.pool_size,
                                    strides=attrs.strides, padding=attrs.padding,
                                    layout=attrs.layout, ceil_mode=attrs.ceil_mode,
                                    count_include_pad=attrs.count_include_pad)
    return [pool_grad]

# not implemented, this is only for testing.
@register_gradient("concatenate")
def concatenate_grad(orig, grad):
    assert len(orig.args) == 1
    t = orig.args[0]
    x = TupleGetItem(t, 0)
    y = TupleGetItem(t, 1)
    # Assume only two element in tuple rn.
    # In the real implementation, concatenate_grad probably need to be implemented by an operator.
    return [Tuple([zeros_like(x), zeros_like(y)])]

@register_gradient("nn.conv2d")
def conv2d_grad(orig, grad):
    """Gradient of conv2d"""
    attrs = orig.attrs
    data, weight = orig.args
    data_shape = get_const_tuple(data.checked_type.shape)
    weight_shape = get_const_tuple(weight.checked_type.shape)
    _, _, grad_h, grad_w = get_const_tuple(orig.checked_type.shape)
    batch, in_channel, in_h, in_w = data_shape
    out_channel, _, filter_h, filter_w = weight_shape

    # infer output_padding
    fpad_top, fpad_left, fpad_bottom, fpad_right = get_pad_tuple(get_const_tuple(attrs.padding),
                                                                 (filter_h, filter_w))
    stride_h, stride_w = get_const_tuple(attrs.strides)
    dilation_h, dilation_w = get_const_tuple(attrs.dilation)
    out_h = (grad_h - 1) * stride_h - fpad_top - fpad_bottom + filter_h
    out_w = (grad_w - 1) * stride_w - fpad_left - fpad_right + filter_w
    output_padding = (in_h - out_h, in_w - out_w)

    assert attrs.data_layout == 'NCHW', 'only support NCHW data layout'
    assert attrs.kernel_layout == 'OIHW', 'only support OIHW kernel layout'
    assert attrs.out_layout in ['', 'NCHW'], 'only support NCHW output layout'


    backward_data = _nn.conv2d_transpose(grad, weight,
                                         strides=attrs.strides,
                                         padding=attrs.padding,
                                         dilation=attrs.dilation,
                                         groups=attrs.groups,
                                         output_padding=output_padding)
    grad = tile(grad, [1, in_channel // attrs.groups, 1, 1])
    grad = reshape(grad, [-1, 1, 0, 0])  # batch * oc * ic // groups, 1, oh, ow
    data = reshape(data, [1, -1, 0, 0])  # 1, batch * ic, ih, iw

    backward_weight = _nn.conv2d(data, grad,
                                 strides=attrs.dilation,
                                 padding=attrs.padding,
                                 dilation=attrs.strides,
                                 groups=in_channel * batch)
    # infer shape of backward_weight
    padded_weight_grad_h = (in_h - (grad_h - 1) * stride_h - 1 + fpad_top + fpad_bottom) \
                           // dilation_h + 1
    padded_weight_grad_w = (in_w - (grad_w - 1) * stride_w - 1 + fpad_left + fpad_right) \
                           // dilation_w + 1
    backward_weight = reshape(backward_weight,
                              [batch, in_channel // attrs.groups, out_channel,
                               padded_weight_grad_h, padded_weight_grad_w])
    backward_weight = _sum(backward_weight, axis=0)
    backward_weight = transpose(backward_weight, [1, 0, 2, 3])

    assert padded_weight_grad_h >= filter_h
    assert padded_weight_grad_w >= filter_w
    if padded_weight_grad_h > filter_h or padded_weight_grad_w > filter_w:
        backward_weight = strided_slice(backward_weight, begin=[0, 0, 0, 0],
                                        end=[None, None, filter_h, filter_w])

    return [backward_data, backward_weight]
