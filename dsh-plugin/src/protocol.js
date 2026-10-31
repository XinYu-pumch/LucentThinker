export const PACKAGE = 'dsh-plugin-lucentthinker';
export const descriptors = ['session', 'status'].map(method => ({
  id: `${PACKAGE}#lucentThinker/${method}`,
  service: 'lucentThinker', namespace: 'lucentThinker', method,
  invocation: {kind: 'direct'}, parameters: [], result: {mode: 'src-json'},
}));
export const contribution = {package: PACKAGE, descriptors};
