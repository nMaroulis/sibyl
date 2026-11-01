import React from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import CodeBlock from '@theme/CodeBlock';

/** Release examples follow synchronized package metadata; historical notes stay fixed. */
export function ReleaseVersion({ prefix = 'v', short = false }) {
  const { siteConfig } = useDocusaurusContext();
  const version = siteConfig.customFields.sibylVersion;
  return (
    <>
      {prefix}
      {short ? version.split('.').slice(0, 2).join('.') : version}
    </>
  );
}

/** Show a copyable command for the version being documented, without duplicating it in Markdown. */
export function PackageInstall({ local = false, extra }) {
  const { siteConfig } = useDocusaurusContext();
  const version = siteConfig.customFields.sibylVersion;
  const filename = `sibyl-${version}-py3-none-any.whl`;
  const repository = `https://github.com/${siteConfig.organizationName}/${siteConfig.projectName}`;
  const location = local
    ? `./dist/${filename}`
    : `${repository}/releases/download/v${version}/${filename}`;
  const requirement = extra ? `"sibyl[${extra}] @ ${location}"` : location;
  return (
    <CodeBlock language="bash">{`uv tool install --python 3.12 ${requirement}\nsibyl --open-browser`}</CodeBlock>
  );
}
