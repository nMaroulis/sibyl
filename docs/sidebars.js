module.exports = {
  guide: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      items: ['getting-started/installation', 'getting-started/configuration'],
    },
    {
      type: 'category',
      label: 'User guide',
      items: [
        'guides/portfolio',
        'guides/exchanges',
        'guides/settings',
        'guides/markets',
        'guides/trading',
        'guides/strategies',
        'guides/strategy-monitor',
        'guides/oracle',
        'guides/research',
        'guides/security',
        'guides/feature-coverage',
      ],
    },
    {
      type: 'category',
      label: 'Developers',
      items: [
        'developers/architecture',
        'developers/agents',
        'developers/api',
        'developers/extending',
        'developers/testing',
        'developers/deployment',
      ],
    },
  ],
};
