import { checkedPath } from './research.mjs';
import { science } from './science.mjs';
import { projectScience, analysisOptions } from './project-science.mjs';

const outputs = ['-result.json', '-input.json', '-report.md', '-data.csv', '-curve.png', '-curve.svg', '-reproduce.py'];
const language = { type: 'string', enum: ['zh', 'en'] };
const parameters = { type: 'object', additionalProperties: true, description: 'Operation parameters from the bundled skill inputs.md. Formulation mixture: stocks:[{concentration:{value,unit},volume:{value,unit},label?:string}], final_volume:{value,unit}. Stocks must contain the same solute.' };

export function registerCalculationTools({ tool, requireProject, ownerFor }) {
  tool('highzyme_formulation', 'Calculate explicit units, amounts, solution preparation, dilution, same-solute mixtures or ratios using Pint. Load formulation-calculations for input examples. Omit output_prefix for a quick numeric answer; provide it to save a project artifact.', {
    parameters: { ...parameters, required: true }, ...analysisOptions, language,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!args.output_prefix && !args.artifact_id && !args.new_analysis) return science({ action: 'calculation', calculation: 'formulation', parameters: args.parameters }, exec.signal);
    return projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'calculation', stem: 'formulation',
      title: args.language === 'zh' ? '配方计算' : 'Formulation calculation', suffixes: outputs,
      input: { calculation: 'formulation' } }, exec.signal);
  });
  tool('highzyme_analyze_signal', 'Analyze project CSV/TSV/XLSX data using a linear calibration fit, a supplied calibration equation, or supplied fluorescence correction factors. Load signal-analysis for column and parameter formats. Saves numeric results, data and report; a fit includes a curve.', {
    file: { type: 'string', required: true }, sheet: { type: 'string' },
    operation: { type: 'string', required: true, enum: ['fit_calibration', 'linear_readout', 'quenching_correction', 'quantify'] },
    columns: { type: 'object', required: true, additionalProperties: true, description: 'fit_calibration: {x: column, y: column}; linear_readout: {concentrations: column}; quenching_correction: {observed: column, correction_factors: column}' },
    parameters: { ...parameters, required: true }, calibration_file: { type: 'string', description: 'Saved calibration -result.json required for quantify' }, ...analysisOptions, language,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (args.operation === 'quantify' && !args.calibration_file) throw new Error('Select a saved calibration result for quantification');
    const stem = { fit_calibration: 'signal-calibration', quantify: 'signal-quantification', linear_readout: 'calibration-evaluation', quenching_correction: 'signal-correction' }[args.operation];
    const result = await projectScience(p, args, ownerFor(p, exec.agent.session), {
      action: 'calculation', stem, title: args.language === 'zh' ? '信号与标定分析' : 'Signal and calibration analysis',
      suffixes: outputs, sources: [args.file, ...(args.calibration_file ? [args.calibration_file] : [])], input: { calculation: 'signal', file: checkedPath(p.root, args.file), source_label: args.file,
        ...(args.calibration_file ? { calibration_file: checkedPath(p.root, args.calibration_file), calibration_label: args.calibration_file } : {}) },
    }, exec.signal);
    return { status: result.status, summary: result.summary, method: result.method, sources: result.sources, files: result.files, artifact: result.artifact };
  });
  tool('highzyme_simulate_reaction', 'Simulate supplied Michaelis-Menten curves, reciprocal-plot parameters or a declared mass-action reaction network. Input is a project JSON following reaction-simulation. This is a local numerical calculation using supplied parameters.', {
    file: { type: 'string', required: true }, ...analysisOptions, language,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    const result = await projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'calculation', stem: 'reaction-simulation',
      title: args.language === 'zh' ? '反应动力学模拟' : 'Reaction kinetics simulation', suffixes: outputs, sources: [args.file],
      input: { calculation: 'reaction', file: checkedPath(p.root, args.file), source_label: args.file } }, exec.signal);
    return { status: result.status, summary: result.summary, method: result.method, sources: result.sources, files: result.files, artifact: result.artifact };
  });
  tool('highzyme_image_colorimetry', 'Measure RGB/HSV statistics in project PNG/JPEG/WebP images using OpenCV. Choose an existing ROI image, a normalized rectangle or detected circles. Saves CSV, report and annotated ROI images; concentrations require separate calibration.', {
    files: { type: 'array', required: true, items: { type: 'string' } },
    mode: { type: 'string', required: true, enum: ['whole_image', 'region', 'circle_rois'] },
    region: { type: 'array', items: { type: 'number' } }, min_radius_fraction: { type: 'number' }, max_radius_fraction: { type: 'number' },
    ...analysisOptions, language,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    if (!args.files.length || args.files.length > 24) throw new Error('Select 1 to 24 images');
    const result = await projectScience(p, args, ownerFor(p, exec.agent.session), { action: 'calculation', stem: 'image-colorimetry',
      title: args.language === 'zh' ? '图像比色' : 'Image colorimetry', sources: args.files,
      suffixes: [...outputs, ...args.files.map((_, i) => '-roi-' + (i+1) + '.png')],
      input: { calculation: 'colorimetry', files: args.files.map(file => checkedPath(p.root, file)), source_labels: args.files } }, exec.signal);
    return { summary: result.summary, images: result.data.images, sources: result.sources, files: result.files, artifact: result.artifact };
  });
  tool('highzyme_replot_analysis', 'Redraw a saved signal or simulation -result.json using its stored numerical series. Changes labels and axes without refitting. For Michaelis-Menten fits use highzyme_replot_kinetics.', {
    file: { type: 'string', required: true }, labels: { type: 'array', items: { type: 'string' } },
    x_label: { type: 'string' }, y_label: { type: 'string' }, ...analysisOptions, language,
  }, async (args, exec) => {
    const p = await requireProject(exec);
    return projectScience(p, args, ownerFor(p, exec.agent.session), {
      action: 'replot_analysis', replot: true, stem: 'analysis', title: args.language === 'zh' ? '分析曲线' : 'Analysis curves',
      sources: [args.file], suffixes: ['-curve.png', '-curve.svg', '-plot.json'], input: { file: checkedPath(p.root, args.file) },
    }, exec.signal);
  });
}
