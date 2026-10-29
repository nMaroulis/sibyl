import React from 'react';
import Layout from '@theme/Layout';
import BrandHero from '../components/BrandHero';

export default function Home() {
  return (
    <Layout
      title="Read the signals. See the bigger picture."
      description="Your exchanges, market research and ProtoLink AI team in one connected crypto workspace. Find your way through Sibyl."
      wrapperClassName="sibyl-home-layout"
    >
      <main className="sibyl-home">
        <BrandHero />
      </main>
    </Layout>
  );
}
