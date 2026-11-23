Pipelines
=========

Die Klassen der unterstützten Paketoberfläche stehen unter
:doc:`../public`. Hier folgen die weiteren Module der Verarbeitungspipeline.

Visuelle Extraktion
-------------------

.. automodule:: grading_pipeline.extraction.visual_extraction
   :members:
   :exclude-members: VisualExtractionPipeline, VisualExtractionResult
   :show-inheritance:

Gemeinsame Aufgabenpipeline
---------------------------

.. automodule:: grading_pipeline.extraction.base
   :members:
   :exclude-members: TaskExtractionResult, TaskPartitioningResult
   :show-inheritance:

Aufgabenextraktion
------------------

.. automodule:: grading_pipeline.extraction.task_extraction
   :members:
   :exclude-members: TaskExtractionPipeline
   :show-inheritance:

Bildsupplemente
---------------

.. automodule:: grading_pipeline.extraction.image_supplements
   :members:
   :show-inheritance:

Aufgabenpartitionierung
-----------------------

.. automodule:: grading_pipeline.extraction.task_partitioning
   :members:
   :exclude-members: TaskPartitioningPipeline
   :show-inheritance:

Rubric-Erzeugung
----------------

.. automodule:: grading_pipeline.rubrics.rubric_generation
   :members:
   :show-inheritance:

Rubric-Ziele
-------------

.. automodule:: grading_pipeline.rubrics.targets
   :members:
   :show-inheritance:

Rubric-Berichte
---------------

.. automodule:: grading_pipeline.rubrics.reporting
   :members:

Bewertung
---------

.. automodule:: grading_pipeline.grading.grading
   :members:
   :exclude-members: GradingPipeline, GradingPipelineResult
   :show-inheritance:

Monolithische Bewertung
-----------------------

.. automodule:: grading_pipeline.grading.monolithic
   :members:
