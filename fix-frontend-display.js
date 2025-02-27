// This script fixes the metrics display in App.js

const fs = require('fs');
const path = require('path');

// Path to App.js
const appJsPath = path.join('frontend', 'src', 'App.js');

// Read the file
fs.readFile(appJsPath, 'utf8', (err, data) => {
  if (err) {
    console.error('Error reading file:', err);
    return;
  }

  // Find the start of the component with metrics display
  const metricsStart = data.indexOf(`{threadMetrics && (`);
  if (metricsStart === -1) {
    console.error('Could not find metrics display section in App.js');
    return;
  }

  // Find the closing brace of the condition
  const closingBrace = data.indexOf(`)}`, metricsStart);
  if (closingBrace === -1) {
    console.error('Could not find end of metrics display section in App.js');
    return;
  }

  // Extract the full conditional section
  const originalSection = data.substring(metricsStart, closingBrace + 2);

  // Create the replacement section that always shows metrics
  const replacementSection = `{/* Always show metrics */}
                <Box sx={{ mt: 2, display: 'flex', gap: 3 }}>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Messages</Typography>
                    <Typography variant="h6">{threadMetrics ? threadMetrics.total_messages : 0}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Input Tokens</Typography>
                    <Typography variant="h6">{threadMetrics ? threadMetrics.total_input_tokens : 0}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Output Tokens</Typography>
                    <Typography variant="h6">{threadMetrics ? threadMetrics.total_output_tokens : 0}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Total Cost</Typography>
                    <Typography variant="h6" color="primary">
                      {threadMetrics ? formatCurrency(threadMetrics.total_cost) : formatCurrency(0)}
                    </Typography>
                  </Box>
                </Box>`;

  // Replace the section in the file content
  const updatedContent = data.replace(originalSection, replacementSection);

  // Write the updated content back to the file
  fs.writeFile(appJsPath, updatedContent, 'utf8', (err) => {
    if (err) {
      console.error('Error writing file:', err);
      return;
    }
    console.log('Successfully updated App.js to always display metrics!');
  });
});