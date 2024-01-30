[![DOI](https://zenodo.org/badge/627515878.svg)](https://zenodo.org/doi/10.5281/zenodo.10594273)

# A two-fold deep learning strategy to correct and downscale winds over mountains.
*Louis Le Toumelin, Isabelle Gouttevin, Clovis Galiez, and Nora Helbig*

#### Abstract
Assessing wind fields at a local scale in mountainous terrain has long been a scientific challenge,
partly because of the complex interaction between large-scale flows and local topography. Traditionally, the
operational applications that require high-resolution wind forcings rely on downscaled outputs of numerical
weather prediction systems. Downscaling models either proceed from a function that links large-scale wind fields
to local observations (hence including a corrective step) or use operations that account for local-scale processes,
through statistics or dynamical simulations and without prior knowledge of large-scale modeling errors. This
work presents a strategy to first correct and then downscale the wind fields of the numerical weather prediction
model AROME (Application of Research to Operations at Mesoscale) operating at 1300 m grid spacing by
using a modular architecture composed of two artificial neural networks and the DEVINECE1 downscaling
model. We show that our method is able to first correct the wind direction and speed from the large-scale model
(1300 m) and then accurately downscale it to a local scale (30 m) by using the DEVINE downscaling model.
The innovative aspect of our method lies in its optimization scheme that accounts for the downscaling step in
the computations of the corrections of the coarse-scale wind fields. This modular architecture yields competitive
results without suppressing the versatility of the DEVINE downscaling model, which remains unbounded to any
wind observations.

#### Use the code
1. Clone the repository
2. Rename it "bias_correction"
