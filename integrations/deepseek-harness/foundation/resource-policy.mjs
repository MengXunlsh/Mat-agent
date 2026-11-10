export const JOB_DEFAULTS = { ranks: 1, threads: 1, memory_mb: 1024, timeout_seconds: 300 };
const bounds = { ranks: 65536, threads: 1024, memory_mb: 2 ** 31, timeout_seconds: 30 * 86400 };

function positiveInteger(value, key) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1 || number > bounds[key]) throw new Error('Invalid resource request: ' + key);
  return number;
}

export function resourcePolicy(input) {
  const defaults = {}, limits = {};
  for (const key of Object.keys(JOB_DEFAULTS)) {
    defaults[key] = positiveInteger(input.defaults?.[key] ?? JOB_DEFAULTS[key], key);
    const limit = input.limits?.[key];
    if (limit !== undefined && limit !== null && limit !== '') {
      limits[key] = positiveInteger(limit, key);
      if (defaults[key] > limits[key]) throw new Error('Default exceeds resource limit: ' + key);
    }
  }
  return { defaults, limits };
}

export function resourceRequest(resource, task) {
  const { defaults, limits } = resourcePolicy(resource), result = {};
  for (const key of Object.keys(JOB_DEFAULTS)) {
    result[key] = positiveInteger(task[key] ?? (key === 'threads' ? task.cores : undefined) ?? defaults[key], key);
    if (limits[key] && result[key] > limits[key]) throw new Error('Resource limit exceeded: ' + key + ' (maximum ' + limits[key] + ')');
  }
  return result;
}
