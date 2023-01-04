import copy
import datetime
import logging
from math import ceil
import os
from typing import Any, Dict, List, Optional, Text

import rasa.nlu
from rasa.shared.exceptions import RasaException
import rasa.shared.utils.io
import rasa.utils.io
from rasa.constants import MINIMUM_COMPATIBLE_VERSION, NLU_MODEL_NAME_PREFIX
from rasa.shared.constants import DOCS_URL_COMPONENTS
from rasa.nlu import components, utils
from rasa.nlu.classifiers.classifier import IntentClassifier
from rasa.nlu.components import Component, ComponentBuilder
from rasa.nlu.config import RasaNLUModelConfig, component_config_from_pipeline
from rasa.nlu.extractors.extractor import EntityExtractor

from rasa.nlu.persistor import Persistor
from rasa.shared.nlu.constants import (
    TEXT,
    ENTITIES,
    INTENT,
    INTENT_NAME_KEY,
    PREDICTED_CONFIDENCE_KEY,
)
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.nlu.training_data.message import Message
from rasa.nlu.utils import write_json_to_file
from rasa.utils.tensorflow.constants import EPOCHS

logger = logging.getLogger(__name__)


class InvalidModelError(RasaException):
    """Raised when a model failed to load.

    Attributes:
        message -- explanation of why the model is invalid
    """

    def __init__(self, message: Text) -> None:
        """Initialize message attribute."""
        self.message = message
        super(InvalidModelError, self).__init__(message)

    def __str__(self) -> Text:
        return self.message


class UnsupportedModelError(RasaException):
    """Raised when a model is too old to be loaded.

    Attributes:
        message -- explanation of why the model is invalid
    """

    def __init__(self, message: Text) -> None:
        """Initialize message attribute."""
        self.message = message
        super(UnsupportedModelError, self).__init__(message)

    def __str__(self) -> Text:
        return self.message


class Metadata:
    """Captures all information about a model to load and prepare it."""

    @staticmethod
    def load(model_dir: Text) -> "Metadata":
        """Loads the metadata from a models directory.

        Args:
            model_dir: the directory where the model is saved.
        Returns:
            Metadata: A metadata object describing the model
        """
        try:
            metadata_file = os.path.join(model_dir, "metadata.json")
            data = rasa.shared.utils.io.read_json_file(metadata_file)
            return Metadata(data)
        except Exception as e:
            abspath = os.path.abspath(os.path.join(model_dir, "metadata.json"))
            raise InvalidModelError(
                f"Failed to load model metadata from '{abspath}'. {e}"
            )

    def __init__(self, metadata: Dict[Text, Any]) -> None:
        """Set `metadata` attribute."""
        self.metadata = metadata

    def get(self, property_name: Text, default: Any = None) -> Any:
        """Proxy function to get property on `metadata` attribute."""
        return self.metadata.get(property_name, default)

    @property
    def component_classes(self) -> List[Optional[Text]]:
        """Returns a list of component class names."""
        if self.get("pipeline"):
            return [c.get("class") for c in self.get("pipeline", [])]
        else:
            return []

    @property
    def number_of_components(self) -> int:
        """Returns count of components."""
        return len(self.get("pipeline", []))

    def for_component(self, index: int, defaults: Any = None) -> Dict[Text, Any]:
        """Returns the configuration of the component based on index."""
        return component_config_from_pipeline(index, self.get("pipeline", []), defaults)

    @property
    def language(self) -> Optional[Text]:
        """Language of the underlying model"""

        return self.get("language")

    def persist(self, model_dir: Text) -> None:
        """Persists the metadata of a model to a given directory."""

        metadata = self.metadata.copy()

        metadata.update(
            {
                "trained_at": datetime.datetime.now().strftime("%Y%m%d-%H%M%S"),
                "rasa_version": rasa.__version__,
            }
        )

        filename = os.path.join(model_dir, "metadata.json")
        write_json_to_file(filename, metadata, indent=4)


class Trainer:
    """Trainer will load the data and train all components.

    Requires a pipeline specification and configuration to use for
    the training.
    """

    def __init__(
        self,
        cfg: RasaNLUModelConfig,
        component_builder: Optional[ComponentBuilder] = None,
        skip_validation: bool = False,
        model_to_finetune: Optional["Interpreter"] = None,
    ) -> None:

        self.config = cfg
        self.skip_validation = skip_validation
        self.training_data = None  # type: Optional[TrainingData]

        if component_builder is None:
            # If no builder is passed, every interpreter creation will result in
            # a new builder. hence, no components are reused.
            component_builder = components.ComponentBuilder()

        # Before instantiating the component classes, lets check if all
        # required packages are available
        if not self.skip_validation:
            components.validate_requirements(cfg.component_names)

        if model_to_finetune:
            self.pipeline = model_to_finetune.pipeline
        else:
            self.pipeline = self._build_pipeline(cfg, component_builder)

    def _build_pipeline(
        self, cfg: RasaNLUModelConfig, component_builder: ComponentBuilder
    ) -> List[Component]:
        """Transform the passed names of the pipeline components into classes."""
        pipeline = []

        # Transform the passed names of the pipeline components into classes
        for index, pipeline_component in enumerate(cfg.pipeline):
            component_cfg = cfg.for_component(index)
            component = component_builder.create_component(component_cfg, cfg)
            components.validate_component_keys(component, pipeline_component)
            pipeline.append(component)

        if not self.skip_validation:
            components.validate_pipeline(pipeline)

        return pipeline

    def train(self, data: TrainingData, **kwargs: Any) -> "Interpreter":
        """Trains the underlying pipeline using the provided training data."""

        self.training_data = data

        self.training_data.validate()

        context = kwargs

        for component in self.pipeline:
            updates = component.provide_context()
            if updates:
                context.update(updates)

        # Before the training starts: check that all arguments are provided
        if not self.skip_validation:
            components.validate_required_components_from_data(
                self.pipeline, self.training_data
            )

        # Warn if there is an obvious case of competing entity extractors
        components.warn_of_competing_extractors(self.pipeline)
        components.warn_of_competition_with_regex_extractor(
            self.pipeline, self.training_data
        )

        # data gets modified internally during the training - hence the copy
        working_data: TrainingData = copy.deepcopy(data)

        for i, component in enumerate(self.pipeline):
            logger.info(f"Starting to train component {component.name}")
            component.prepare_partial_processing(self.pipeline[:i], context)
            component.train(working_data, self.config, **context)
            logger.info("Finished training component.")

        return Interpreter(self.pipeline, context)

    @staticmethod
    def _file_name(index: int, name: Text) -> Text:
        return f"component_{index}_{name}"

    def persist(
        self,
        path: Text,
        persistor: Optional[Persistor] = None,
        fixed_model_name: Text = None,
        persist_nlu_training_data: bool = False,
    ) -> Text:
        """Persist all components of the pipeline to the passed path.

        Returns the directory of the persisted model."""

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        metadata = {"language": self.config["language"], "pipeline": []}

        if fixed_model_name:
            model_name = fixed_model_name
        else:
            model_name = NLU_MODEL_NAME_PREFIX + timestamp

        path = os.path.abspath(path)
        dir_name = os.path.join(path, model_name)

        rasa.shared.utils.io.create_directory(dir_name)

        if self.training_data and persist_nlu_training_data:
            metadata.update(self.training_data.persist(dir_name))

        for i, component in enumerate(self.pipeline):
            file_name = self._file_name(i, component.name)
            update = component.persist(file_name, dir_name)
            component_meta = component.component_config
            if update:
                component_meta.update(update)
            component_meta["class"] = utils.module_path_from_object(component)

            metadata["pipeline"].append(component_meta)

        Metadata(metadata).persist(dir_name)

        if persistor is not None:
            persistor.persist(dir_name, model_name)
        logger.info(
            "Successfully saved model into '{}'".format(os.path.abspath(dir_name))
        )
        return dir_name


class Interpreter:
    """Use a trained pipeline of components to parse text messages."""

    # Defines all attributes (& default values)
    # that will be returned by `parse`
    @staticmethod
    def default_output_attributes() -> Dict[Text, Any]:
        return {
            TEXT: "",
            INTENT: {INTENT_NAME_KEY: None, PREDICTED_CONFIDENCE_KEY: 0.0},
            ENTITIES: [],
        }

    @staticmethod
    def ensure_model_compatibility(
        metadata: Metadata, version_to_check: Optional[Text] = None
    ) -> None:
        from packaging import version

        if version_to_check is None:
            version_to_check = MINIMUM_COMPATIBLE_VERSION

        model_version = metadata.get("rasa_version", "0.0.0")
        if version.parse(model_version) < version.parse(version_to_check):
            raise UnsupportedModelError(
                f"The model version is trained using Rasa Open Source {model_version} "
                f"and is not compatible with your current installation "
                f"({rasa.__version__}). "
                f"This means that you either need to retrain your model "
                f"or revert back to the Rasa version that trained the model "
                f"to ensure that the versions match up again."
            )

    @staticmethod
    def load(
        model_dir: Text,
        component_builder: Optional[ComponentBuilder] = None,
        skip_validation: bool = False,
        new_config: Optional[Dict] = None,
        finetuning_epoch_fraction: float = 1.0,
    ) -> "Interpreter":
        """Create an interpreter based on a persisted model.

        Args:
            skip_validation: If set to `True`, does not check that all
                required packages for the components are installed
                before loading them.
            model_dir: The path of the model to load
            component_builder: The
                :class:`rasa.nlu.components.ComponentBuilder` to use.
            new_config: Optional new config to use for the new epochs.
            finetuning_epoch_fraction: Value to multiply all epochs by.

        Returns:
            An interpreter that uses the loaded model.
        """
        model_metadata = Metadata.load(model_dir)

        if new_config:
            Interpreter._update_metadata_epochs(
                model_metadata, new_config, finetuning_epoch_fraction
            )

        Interpreter.ensure_model_compatibility(model_metadata)
        return Interpreter.create(
            model_dir,
            model_metadata,
            component_builder,
            skip_validation,
            should_finetune=new_config is not None,
        )

    @staticmethod
    def _get_default_value_for_component(name: Text, key: Text) -> Any:
        from rasa.nlu.registry import get_component_class

        return get_component_class(name).defaults[key]

    @staticmethod
    def _update_metadata_epochs(
        model_metadata: Metadata,
        new_config: Optional[Dict] = None,
        finetuning_epoch_fraction: float = 1.0,
    ) -> Metadata:
        for old_component_config, new_component_config in zip(
            model_metadata.metadata["pipeline"], new_config["pipeline"]
        ):
            if EPOCHS in old_component_config:
                new_epochs = new_component_config.get(
                    EPOCHS,
                    Interpreter._get_default_value_for_component(
                        old_component_config["class"], EPOCHS
                    ),
                )
                old_component_config[EPOCHS] = ceil(
                    new_epochs * finetuning_epoch_fraction
                )
        return model_metadata

    @staticmethod
    def create(
        model_dir: Text,
        model_metadata: Metadata,
        component_builder: Optional[ComponentBuilder] = None,
        skip_validation: bool = False,
        should_finetune: bool = False,
    ) -> "Interpreter":
        """Create model and components defined by the provided metadata.

        Args:
            model_dir: The directory containing the model.
            model_metadata: The metadata describing each component.
            component_builder: The
                :class:`rasa.nlu.components.ComponentBuilder` to use.
            skip_validation: If set to `True`, does not check that all
                required packages for the components are installed
                before loading them.
            should_finetune: Indicates if the model components will be fine-tuned.

        Returns:
            An interpreter that uses the created model.
        """
        context: Dict[Text, Any] = {"should_finetune": should_finetune}

        if component_builder is None:
            # If no builder is passed, every interpreter creation will result
            # in a new builder. hence, no components are reused.
            component_builder = components.ComponentBuilder()

        pipeline = []

        # Before instantiating the component classes,
        # lets check if all required packages are available
        if not skip_validation:
            components.validate_requirements(model_metadata.component_classes)

        for i in range(model_metadata.number_of_components):
            component_meta = model_metadata.for_component(i)
            component = component_builder.load_component(
                component_meta, model_dir, model_metadata, **context
            )
            try:
                updates = component.provide_context()
                if updates:
                    context.update(updates)
                pipeline.append(component)
            except components.MissingArgumentError as e:
                raise Exception(
                    "Failed to initialize component '{}'. "
                    "{}".format(component.name, e)
                )

        return Interpreter(pipeline, context, model_metadata)

    def __init__(
        self,
        pipeline: List[Component],
        context: Optional[Dict[Text, Any]],
        model_metadata: Optional[Metadata] = None,
    ) -> None:

        self.pipeline = pipeline
        self.context = context if context is not None else {}
        self.model_metadata = model_metadata
        self.has_already_warned_of_overlapping_entities = False

    def parse(
        self,
        text: Text,
        time: Optional[datetime.datetime] = None,
        only_output_properties: bool = True,
    ) -> Dict[Text, Any]:
        """Parse the input text, classify it and return pipeline result.

        The pipeline result usually contains intent and entities."""

        if not text:
            # Not all components are able to handle empty strings. So we need
            # to prevent that... This default return will not contain all
            # output attributes of all components, but in the end, no one
            # should pass an empty string in the first place.
            output = self.default_output_attributes()
            output["text"] = ""
            return output

        timestamp = int(time.timestamp()) if time else None
        data = self.default_output_attributes()
        data[TEXT] = text

        message = Message(data=data, time=timestamp)

        for component in self.pipeline:
            component.process(message, **self.context)

        if not self.has_already_warned_of_overlapping_entities:
            self.warn_of_overlapping_entities(message)

        output = self.default_output_attributes()
        output.update(message.as_dict(only_output_properties=only_output_properties))
        return output

    def featurize_message(self, message: Message) -> Message:
        """
        Tokenize and featurize the input message
        Args:
            message: message storing text to process;
        Returns:
            message: it contains the tokens and features which are the output of the
            NLU pipeline;
        """

        for component in self.pipeline:
            if not isinstance(component, (EntityExtractor, IntentClassifier)):
                component.process(message, **self.context)
        return message

    def warn_of_overlapping_entities(self, message: Message) -> None:
        """Issues a warning when there are overlapping entity annotations.

        This warning is only issued once per Interpreter life time.

        Args:
            message: user message with all processing metadata such as entities
        """
        overlapping_entity_pairs = message.find_overlapping_entities()
        if len(overlapping_entity_pairs) > 0:
            message_text = message.get("text")
            first_pair = overlapping_entity_pairs[0]
            entity_1 = first_pair[0]
            entity_2 = first_pair[1]
            rasa.shared.utils.io.raise_warning(
                f"Parsing of message: '{message_text}' lead to overlapping "
                f"entities: {entity_1['value']} of type "
                f"{entity_1['entity']} extracted by "
                f"{entity_1['extractor']} overlaps with "
                f"{entity_2['value']} of type {entity_2['entity']} extracted by "
                f"{entity_2['extractor']}. This can lead to unintended filling of "
                f"slots. Please refer to the documentation section on entity "
                f"extractors and entities getting extracted multiple times:"
                f"{DOCS_URL_COMPONENTS}#entity-extractors"
            )
            self.has_already_warned_of_overlapping_entities = True
