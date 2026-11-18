import React from 'react';
import { ChaosBuilderCard } from './ChaosBuilderCard';

export const App: React.FC = () => {
  return (
    <div style={{ padding: '20px 10px' }}>
      <ChaosBuilderCard
        apiBasePath=""
        githubHandle="Viditya"
        sandboxName="mcp-chaos-prod (2 vCPU / 4 GiB Cloud microVM)"
      />
    </div>
  );
};

export default App;
