import { checkedPath } from './research.mjs';
import { projectScience } from './project-science.mjs';

export async function fitProjectKinetics(project, args, owner, signal) {
  const suffixes = ['-data.csv', '-result.json', '-report.md', '-curve.png', '-curve.svg', '-input.json', '-reproduce.py', '-plot.json'];
  if (args.group_columns?.length) suffixes.push('-parameters.csv');
  return projectScience(project, args, owner, { action: 'fit_kinetics', stem: 'initial-rate',
    title: args.language === 'zh' ? '初始速率动力学拟合' : 'Initial-rate kinetics fit', sources: [args.file], suffixes,
    input: { file: checkedPath(project.root, args.file), source_label: args.file } }, signal);
}

export async function replotProjectKinetics(project, args, owner, signal) {
  return projectScience(project, args, owner,
    { action: 'replot_kinetics', replot: true, stem: 'kinetics-curve', title: args.language === 'zh' ? '动力学曲线' : 'Kinetics curves',
      sources: [args.file], suffixes: ['-curve.png', '-curve.svg', '-plot.json'],
      input: { file: checkedPath(project.root, args.file), source_label: args.file } }, signal);
}
