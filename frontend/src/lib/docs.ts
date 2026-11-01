/** A packaged dashboard needs no local Docusaurus process; development keeps its preview. */
export const DOCUMENTATION_URL = import.meta.env.DEV
  ? 'http://localhost:3000/sibyl/'
  : 'https://nmaroulis.github.io/sibyl/';
