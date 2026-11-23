Öffentliche API
===============

Diese Seite dokumentiert die acht Namen aus ``grading_pipeline.__all__``.
Sie sind direkt aus ``grading_pipeline`` importierbar. Die Referenz
verwendet die Module, in denen die Klassen definiert sind, damit die
Quellcodeansichten zu den richtigen Klassen und Methoden zurückverlinken.

.. code-block:: python

   from grading_pipeline import (
       GradingPipeline,
       GradingPipelineResult,
       TaskExtractionPipeline,
       TaskExtractionResult,
       TaskPartitioningPipeline,
       TaskPartitioningResult,
       VisualExtractionPipeline,
       VisualExtractionResult,
   )

Weitere Module beschreibt die :doc:`Entwicklerreferenz <developer/index>`.

Visuelle Extraktion
-------------------

.. autoclass:: grading_pipeline.extraction.visual_extraction.VisualExtractionPipeline
   :members: extract

.. autoclass:: grading_pipeline.extraction.visual_extraction.VisualExtractionResult
   :members:

Aufgabenextraktion
------------------

.. autoclass:: grading_pipeline.extraction.task_extraction.TaskExtractionPipeline
   :members: extract

.. autoclass:: grading_pipeline.extraction.base.TaskExtractionResult
   :members:

Aufgabenpartitionierung
-----------------------

.. autoclass:: grading_pipeline.extraction.task_partitioning.TaskPartitioningPipeline
   :members: extract

.. autoclass:: grading_pipeline.extraction.base.TaskPartitioningResult
   :members:

Bewertung
---------

.. autoclass:: grading_pipeline.grading.grading.GradingPipeline
   :members: grade

.. autoclass:: grading_pipeline.grading.grading.GradingPipelineResult
   :members:
