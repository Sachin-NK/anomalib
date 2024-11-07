"""DFM: Deep Feature Modeling.

https://arxiv.org/abs/1909.11786
"""

# Copyright (C) 2022-2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any

import torch
from lightning.pytorch.utilities.types import STEP_OUTPUT

from anomalib import LearningType
from anomalib.data import Batch
from anomalib.metrics import Evaluator
from anomalib.models.components import AnomalyModule, MemoryBankMixin
from anomalib.post_processing import PostProcessor

from .torch_model import DFMModel

logger = logging.getLogger(__name__)


class Dfm(MemoryBankMixin, AnomalyModule):
    """DFM: Deep Featured Kernel Density Estimation.

    Args:
        backbone (str): Backbone CNN network
            Defaults to ``"resnet50"``.
        layer (str): Layer to extract features from the backbone CNN
            Defaults to ``"layer3"``.
        pre_trained (bool, optional): Boolean to check whether to use a pre_trained backbone.
            Defaults to ``True``.
        pooling_kernel_size (int, optional): Kernel size to pool features extracted from the CNN.
            Defaults to ``4``.
        pca_level (float, optional): Ratio from which number of components for PCA are calculated.
            Defaults to ``0.97``.
        score_type (str, optional): Scoring type. Options are `fre` and `nll`.
            Defaults to ``fre``.
    """

    def __init__(
        self,
        backbone: str = "resnet50",
        layer: str = "layer3",
        pre_trained: bool = True,
        pooling_kernel_size: int = 4,
        pca_level: float = 0.97,
        score_type: str = "fre",
        post_processor: PostProcessor | None = None,
        evaluator: Evaluator | bool = True,
    ) -> None:
        super().__init__(post_processor=post_processor, evaluator=evaluator)

        self.model: DFMModel = DFMModel(
            backbone=backbone,
            pre_trained=pre_trained,
            layer=layer,
            pooling_kernel_size=pooling_kernel_size,
            n_comps=pca_level,
            score_type=score_type,
        )
        self.embeddings: list[torch.Tensor] = []
        self.score_type = score_type

    @staticmethod
    def configure_optimizers() -> None:  # pylint: disable=arguments-differ
        """DFM doesn't require optimization, therefore returns no optimizers."""
        return

    def training_step(self, batch: Batch, *args, **kwargs) -> None:
        """Perform the training step of DFM.

        For each batch, features are extracted from the CNN.

        Args:
            batch (Batch): Input batch
            args: Arguments.
            kwargs: Keyword arguments.

        Returns:
          Deep CNN features.
        """
        del args, kwargs  # These variables are not used.

        embedding = self.model.get_features(batch.image).squeeze()
        self.embeddings.append(embedding)

    def fit(self) -> None:
        """Fit a PCA transformation and a Gaussian model to dataset."""
        logger.info("Aggregating the embedding extracted from the training set.")
        embeddings = torch.vstack(self.embeddings)

        logger.info("Fitting a PCA and a Gaussian model to dataset.")
        self.model.fit(embeddings)

    def validation_step(self, batch: Batch, *args, **kwargs) -> STEP_OUTPUT:
        """Perform the validation step of DFM.

        Similar to the training step, features are extracted from the CNN for each batch.

        Args:
          batch (Batch): Input batch
          args: Arguments.
          kwargs: Keyword arguments.

        Returns:
          Dictionary containing FRE anomaly scores and anomaly maps.
        """
        del args, kwargs  # These variables are not used.

        predictions = self.model(batch.image)
        return batch.update(**predictions._asdict())

    @property
    def trainer_arguments(self) -> dict[str, Any]:
        """Return DFM-specific trainer arguments."""
        return {"gradient_clip_val": 0, "max_epochs": 1, "num_sanity_val_steps": 0}

    @property
    def learning_type(self) -> LearningType:
        """Return the learning type of the model.

        Returns:
            LearningType: Learning type of the model.
        """
        return LearningType.ONE_CLASS
