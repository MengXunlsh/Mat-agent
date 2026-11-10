---
name: image-colorimetry
description: Measure RGB/HSV statistics in explicit PNG/JPEG/WebP image regions and save measurements plus annotated sampling images.
---

Use `highzyme_image_colorimetry` on authorized project images. Choose `whole_image` for an already cropped ROI, `region` for normalized [left,top,right,bottom], or `circle_rois` for explicit circular-vessel detection. Inspect the source image with native `read_image` before choosing a region; do not guess a crop from a filename.

The local OpenCV tool measures the actual selected pixels. It saves per-region RGB means/standard deviations, HSV means, pixel counts and annotated ROI images. OpenCV H uses 0..179; S and V use 0..255. Circle detection measures the inner region to avoid the vessel rim. A failed detection is returned as such; use an explicit rectangle if the user chooses one.

Inspect the annotated output to check the sampled area. Compare images only with the supplied imaging context in mind. Pixel color alone does not determine analyte concentration; use an appropriate calibration from the same acquisition conditions for quantitative interpretation. Keep image-to-sample mapping in the analysis table when combining this output with signal-analysis.
