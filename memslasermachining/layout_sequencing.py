"""
Module containing the 'LayoutSequencer' class, which generates the laser machining sequence for entire layouts.
"""

from typing import Callable, Any, Self
from functools import wraps
import numpy as np
from numpy.typing import ArrayLike
from config import DEFAULT_TARGET_INIT_SEPARATION
from points import Point, PointArray
from polygon_sequencing import PolygonSequencer, PolygonSequencingError
from visualization import animate_sequence

class LayoutSequencer:
    """
    Generates the laser machining sequence for entire layouts.
    """
    def __init__(self) -> None:
        self.polygons_as_vertices: list[PointArray] = None
        self.num_polygons: int = None
        self.target_init_separation: list[float] = None
        self.staggered: bool = False
        self.polygon_sequencers: list[PolygonSequencer] = None
        self.sequence: list[list[Point]] = None
    
    def validate_state(attribute_name: str) -> Callable:
        """
        Decorator to validate that a specific attribute is not None.
        """
        def decorator(method: Callable) -> Callable:
            @wraps(method)
            def wrapper(self, *args: Any, **kwargs: Any) -> Any:
                if getattr(self, attribute_name) is None:
                    error_message_roots = {"polygons_as_vertices" : "Set polygons",
                                           "sequence" : "Generate sequence"}
                    error_message = error_message_roots[attribute_name] + " before invoking " + method.__name__ + "()"
                    raise RuntimeError(error_message)
                return method(self, *args, **kwargs)
            return wrapper
        return decorator
    
    def set_polygons(self, polygons_as_vertices: list[ArrayLike]) -> Self:
        """
        Sets the layout (list of polygons) to be laser machined.
        Each ArrayLike instance in argument 'polygons_as_vertices' must be of shape [N][2].
        Provide polygons in the desired machining order.
        """
        self.polygons_as_vertices = []
        for vertices_arraylike in polygons_as_vertices:
            # Try to convert ArrayLike of vertices to NDArray
            try:
                vertices_ndarray = np.array(vertices_arraylike, dtype = np.float64, copy = False)
            except (TypeError, ValueError):
                raise ValueError("Input arrays cannot be converted to numpy arrays")
            # Check NDArray of vertices has correct shape
            if vertices_ndarray.ndim!= 2 or vertices_ndarray.shape[1] != 2:
                raise ValueError("Input arrays violate [N][2] shape requirement")
            # Convert NDArray of vertices to PointArray before storing
            self.polygons_as_vertices.append(PointArray(vertices_ndarray))
        # Set target initial pass separation to default
        self.num_polygons = len(self.polygons_as_vertices)
        self.target_init_separation = [DEFAULT_TARGET_INIT_SEPARATION for _ in range(self.num_polygons)]
        return self

    @validate_state('polygons_as_vertices')
    def set_target_init_separation(self, target_init_separation_um: float | list[float]) -> Self:
        """
        Sets the targeted initial pass separation between adjacent hole centers in microns (µm) for each polygon (actual value will vary due to rounding).
        Provide as many values as polygons, or a single value for all polygons.
        """
        if isinstance(target_init_separation_um, list):
            if len(target_init_separation_um) != self.num_polygons:
                raise ValueError("List of target initial pass separations does not match the number of polygons")
            self.target_init_separation = target_init_separation_um
        else:
            self.target_init_separation = [target_init_separation_um for _ in range(self.num_polygons)]
        return self

    def set_staggered(self, staggered: bool) -> Self:
        """
        If argument 'stagger' is True, the laser machining passes of all polygons are merged.
        Otherwise, individual polygons are machined to completion before moving to the next (default).
        """
        self.staggered = staggered
        return self
    
    @validate_state('polygons_as_vertices')
    def generate_sequence(self) -> Self:
        """
        Generates the laser machining sequence for the loaded layout.
        Set all required configurations before calling this method.
        """
        # Try to sequence polygons
        num_passes_by_polygon = []
        self.polygon_sequencers = []
        for polygon_index in range(self.num_polygons):    
            vertices = self.polygons_as_vertices[polygon_index]
            target_init_separation = self.target_init_separation[polygon_index]
            try:
                polygon_sequencer = PolygonSequencer(vertices, target_init_separation)
            except PolygonSequencingError as error:
                raise ValueError(f"Polygons could not be sequenced\n{error}")
            num_passes_by_polygon.append(polygon_sequencer.params.num_passes)
            self.polygon_sequencers.append(polygon_sequencer)
        # Generate global machining sequence
        if self.staggered:
            max_num_passes = max(num_passes_by_polygon)
            self.sequence = [[] for _ in range(max_num_passes)]
            for polygon_sequencer in self.polygon_sequencers:
                for pass_index in range(polygon_sequencer.params.num_passes):
                    self.sequence[pass_index].extend(polygon_sequencer.sequence[pass_index])
        else:
            self.sequence = []
            for polygon_sequencer in self.polygon_sequencers:
                self.sequence.extend(polygon_sequencer.sequence)
        return self

    @validate_state('sequence')
    def view_sequence(self, individually: bool = False, animation_interval_ms: int = 200) -> None:
        """
        Animates the laser machining sequence of the loaded layout. Each color represents a different pass.
        If argument 'individually' is True, each polygon's sequence is shown individually.
        """
        if individually:
            for polygon_sequencer in self.polygon_sequencers:
                polygon_sequencer.view_sequence(animation_interval_ms)
        else:
            polygons_as_vertices_merged = PointArray.concatenate(self.polygons_as_vertices)
            animate_sequence(polygons_as_vertices_merged, self.sequence, animation_interval_ms)