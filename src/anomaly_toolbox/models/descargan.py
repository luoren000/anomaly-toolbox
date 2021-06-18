"""DeScarGAN models."""

from abc import abstractmethod
from typing import List

import tensorflow as tf
import tensorflow.keras as k


class DeScarGANModel(k.Model):  # pylint: disable=too-many-ancestors
    """Methods shared across the DeScarGAN models."""

    def __init__(self, batch_norm: bool):
        """Configure the layers.
        Args:
            batch_norm: enable/disable batch normalization in the network description.
        """
        super().__init__()
        self._batch_norm = batch_norm

        self._bias_initializer = None
        self._kernel_initializer = None

    @property
    @abstractmethod
    def kernel_initializer(self):
        pass

    @property
    @abstractmethod
    def bias_initializer(self):
        pass

    def conv(
        self,
        input_shape,
        filters,
        kernel_size=3,
        momentum=0.01,
        activation_fn=k.layers.ReLU,
    ):
        """Convolutional layer (with or without batch norm depending on the __init__).
        Args:
            input_shape: layer input shape
            filters: number of convolutional filters to learn (the depth of the output volume)
            kernel_size: the size of the kernel to use
            momentum: if batch norm is enabled, the momentum for this layer.
            activation_fn: the activation function to use.
        Returns:
            The convolution operation correctly configured (as a keras model/layer).
        """
        return k.Sequential(
            [
                k.layers.Conv2D(
                    input_shape=input_shape,
                    filters=filters,
                    kernel_size=kernel_size,
                    padding="SAME",
                    kernel_initializer=self.kernel_initializer,
                    bias_initializer=self.bias_initializer,
                    use_bias=not self._batch_norm,
                ),
            ]
            + [k.layers.BatchNormalization(momentum=momentum)]
            if self._batch_norm
            else []
            + [
                activation_fn(),
            ]
        )

    @staticmethod
    def deconv(
        input_shape,
        filters,
        use_upsample=True,
        kernel_size=4,
        strides=2,
        padding="SAME",
        momentum=0.01,
        activation_fn=k.layers.ReLU,
    ):
        """DeConvolutional layer (with or without batch norm depending on the __init__).
        Args:
            input_shape: layer input shape
            filters: number of convolutional filters to learn (the depth of the output volume)
            use_upsample: when True use the upsampling, otherwise conv2d transpose is used.
            kernel_size: the size of the kernel to use
            strides: the stride to use when using conv2d transpose (use_upsample=False)
            padidng: the padding to use when using conv2d transpose (use_upsample=False)
            momentum: if batch norm is enabled, the momentum for this layer.
            activation_fn: the activation function to use.
        Returns:
            The convolution operation correctly configured (as a keras model/layer).
        """
        if use_upsample:
            up_layer = k.Sequential(
                [
                    k.layers.UpSampling2D(),
                    k.layers.Conv2D(
                        input_shape=input_shape,
                        filters=filters,
                        kernel_size=3,
                        strides=1,
                        padding="SAME",
                    ),
                ]
            )
        else:
            up_layer = k.layers.Conv2DTranspose(
                input_shape=input_shape,
                filters=filters,
                kernel_size=kernel_size,
                strides=strides,
                padding=padding,
            )

        return k.Sequential(
            [
                up_layer,
                k.layers.BatchNormalization(momentum=momentum),
                activation_fn(),
            ]
        )

    @staticmethod
    def concat(upsampled, bypass):
        """Concatenate bypass and upsampled in the depth dimension.
        Args:
            upsampled: the input batch
            bypass: the skip connection to concatenate
        Return:
            a new tensor with shape (N, H, W, C1 + C2)
        """
        return tf.concat([upsampled, bypass], axis=-1)

    @staticmethod
    def dense(input_shape, units, momentum=0.01, activation_fn=k.layers.ReLU):
        """Fully connected layer. Using/not using batch norm depending on the object configuration.
        Args:
            input_shape: layer input shape
            units: number of neurons
            momentum: if batch norm is enabled, the momentum for this layer.
            activation_fn: the activation function to use.
        Returns:
            The fully connected layer.
        """

        return k.Sequential(
            [
                k.layers.Dense(input_shape=input_shape, units=units),
                k.layers.BatchNormalization(momentum=momentum),
                activation_fn(),
            ]
        )


class Generator(DeScarGANModel):  # pylint: disable=too-many-ancestors
    """Image generator."""

    def __init__(self, ill_label, n_channels=1, nf=64, batch_norm=True):
        super().__init__(batch_norm)

        self._ill_label = tf.constant(ill_label, dtype=tf.int32)
        self._c_dim = 2
        self._max_pool_fn = k.layers.MaxPool2D

        self._down0 = k.Sequential(
            [
                self.conv((None, None, n_channels + self._c_dim), nf),
                self.conv((None, None, nf), nf),
            ]
        )
        self._down1 = k.Sequential(
            [
                self._max_pool_fn(),
                self.conv((None, None, nf), nf * 2),
                self.conv((None, None, nf * 2), nf * 2),
            ]
        )
        self._down2 = k.Sequential(
            [
                self._max_pool_fn(),
                self.conv((None, None, nf * 2), nf * 4),
                self.conv((None, None, nf * 4), nf * 4),
            ]
        )
        self._down3 = k.Sequential(
            [
                self._max_pool_fn(),
                self.conv((None, None, nf * 4), nf * 8),
                self.conv((None, None, nf * 8), nf * 8),
            ]
        )

        self._up3 = self.deconv((None, None, nf * 8), nf * 4)

        self._conv5 = k.Sequential(
            [
                self.conv((None, None, nf * 8), nf * 4),
                self.conv((None, None, nf * 4), nf * 4),
            ]
        )

        self._up2 = self.deconv((None, None, nf * 4), nf * 2)

        self._conv6 = k.Sequential(
            [
                self.conv((None, None, nf * 4), nf * 2),
                self.conv((None, None, nf * 2), nf * 2),
            ]
        )

        self._up1 = self.deconv((None, None, nf * 2), nf)

        self._conv7_ill = k.Sequential(
            [
                self.conv((None, None, nf), nf),
                self.conv(
                    (None, None, nf), n_channels, activation_fn=k.activations.tanh
                ),
            ]
        )
        self._conv7_healty = k.Sequential(
            [
                self.conv((None, None, nf), nf),
                self.conv(
                    (None, None, nf), n_channels, activation_fn=k.activations.tanh
                ),
            ]
        )

    @property
    def kernel_initializer(self):
        """kaiming_normal_  in the paper -> HeNormal for keras.
        There are minor differences:
        https://stats.stackexchange.com/questions/484062/he-normal-keras-is-truncated-when-kaiming-normal-pytorch-is-not
        """
        if not self._kernel_initializer:
            self._kernel_initializer = k.initializers.HeNormal()
        return self._kernel_initializer

    @property
    def bias_initializer(self):
        """Zero initializer."""
        if not self._bias_initializer:
            self._bias_initializer = k.initializers.Zeros()
        return self._bias_initializer

    def call(self, inputs: List[tf.Tensor], training=False):
        x, label = inputs
        one_hot_label = tf.one_hot(label, depth=2, dtype=tf.float32)
        condition = tf.tile(
            one_hot_label[:, tf.newaxis, tf.newaxis, :],
            [1, tf.shape(x)[1], tf.shape(x)[2], 1],
        )
        x = tf.concat([x, condition], axis=-1)

        input_0 = self._down0(x, training=training)
        input_1 = self._down1(input_0, training=training)
        input_2 = self._down2(input_1, training=training)
        input_3 = self._down3(input_2, training=training)

        input_upsampled_3 = self._up3(input_3, training=training)
        cat3 = self.concat(input_upsampled_3, input_2)
        input_5 = self._conv5(cat3, training=training)
        input_upsampled_2 = self._up2(input_5, training=training)
        cat2 = self.concat(input_upsampled_2, input_1)

        input_6 = self._conv6(cat2, training=training)
        input_upsampled_1 = self._up1(input_6, training=training)

        return tf.cond(
            tf.reduce_all(tf.equal(self._ill_label, tf.cast(label, tf.int32))),
            lambda: self._conv7_ill(input_upsampled_1),
            lambda: self._conv7_healty(input_upsampled_1),
        )


class Discriminator(DeScarGANModel):  # pylint: disable=too-many-ancestors
    """Image discriminator."""

    def __init__(self, ill_label, n_channels=1, nf=64, batch_norm=True):
        super().__init__(batch_norm)

        self._ill_label = tf.constant(ill_label, dtype=tf.int32)
        self._max_pool_fn = k.layers.MaxPool2D

        self._encoder = k.Sequential(
            [
                self.conv((None, None, n_channels), nf),
                self._max_pool_fn(),
                self.conv((None, None, nf), nf * 2),
                self._max_pool_fn(),
                self.conv((None, None, nf * 2), nf * 4),
                self.conv((None, None, nf * 4), nf * 4),
                self._max_pool_fn(),
                self.conv((None, None, nf * 4), nf * 8),
                self.conv((None, None, nf * 8), nf * 8),
                self._max_pool_fn(),
                self.conv((None, None, nf * 8), nf * 8),
                self.conv((None, None, nf * 8), nf * 8),
                self._max_pool_fn(),
                self.conv((None, None, nf * 8), nf * 16),
            ]
        )

        self._conv_ill = k.Sequential(
            [
                self.conv((None, None, nf * 16), nf * 16),
                self.conv((None, None, nf * 16), nf * 16),
                self.conv(
                    (None, None, nf * 16), 1, kernel_size=1, activation_fn=tf.identity
                ),
            ]
        )
        self._conv_healty = k.Sequential(
            [
                self.conv((None, None, nf * 16), nf * 16),
                self.conv((None, None, nf * 16), nf * 16),
                self.conv(
                    (None, None, nf * 16), 1, kernel_size=1, activation_fn=tf.identity
                ),
            ]
        )

        self._conv2 = k.Sequential(
            [
                self.conv((None, None, nf * 16), nf * 16),
                self.conv((None, None, nf * 16), nf * 16),
                self._max_pool_fn(),
            ]
        )

        self._linearclass = k.Sequential(
            [
                k.layers.Flatten(),
                k.layers.Dense(64),
                k.layers.ReLU(),
                k.layers.Dropout(0.1),
                k.layers.Dense(2),
            ]
        )

    @property
    def kernel_initializer(self):
        """Xavier normal"""
        if not self._kernel_initializer:
            self._kernel_initializer = k.initializers.GlorotNormal()
        return self._kernel_initializer

    @property
    def bias_initializer(self):
        """Zero initializer."""
        if not self._bias_initializer:
            self._bias_initializer = k.initializers.Zeros()
        return self._bias_initializer

    def call(self, inputs: List[tf.Tensor], training=False):
        x, label = inputs
        hidden = self._encoder(x, training=training)
        out = tf.cond(
            tf.reduce_all(tf.equal(self._ill_label, tf.cast(label, tf.int32))),
            lambda: self._conv_ill(hidden, training=training),
            lambda: self._conv_healty(hidden, training=training),
        )
        conv = self._conv2(hidden, training=training)
        pred = self._linearclass(tf.squeeze(conv, axis=[1, 2]), training=training)
        return out, pred
