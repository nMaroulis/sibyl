const config = {
  title: 'Sibyl',
  tagline: 'Your connected crypto workspace.',
  favicon: 'img/favicon.svg',
  url: 'https://nmaroulis.github.io',
  baseUrl: '/sibyl/',
  organizationName: 'nMaroulis',
  projectName: 'sibyl',
  onBrokenLinks: 'throw',
  markdown: { hooks: { onBrokenMarkdownLinks: 'throw' } },
  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.js',
          routeBasePath: '/',
          editUrl: 'https://github.com/nMaroulis/sibyl/edit/main/docs/',
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
      },
    ],
  ],
  themeConfig: {
    colorMode: { defaultMode: 'light', respectPrefersColorScheme: false, disableSwitch: true },
    navbar: {
      title: 'Sibyl Docs',
      logo: { alt: 'Sibyl', src: 'img/favicon.svg' },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'guide',
          label: 'Documentation',
          position: 'left',
        },
        {
          href: 'https://github.com/nMaroulis/sibyl',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      copyright: 'Sibyl · Apache 2.0.',
    },
    prism: {
      additionalLanguages: ['python', 'bash', 'json', 'docker', 'yaml'],
    },
  },
};
module.exports = config;
