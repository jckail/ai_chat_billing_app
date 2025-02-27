// Simple script to fix the JSX syntax error in App.js

const fs = require('fs');

// Path to App.js
const appJsPath = 'frontend/src/App.js';

// Read the file
fs.readFile(appJsPath, 'utf8', (err, data) => {
  if (err) {
    console.error(`Error reading file: ${err}`);
    return;
  }

  // Find and fix the specific syntax error
  // Replace lines 566-587 with a corrected version
  const fixedContent = data.replace(
    /{threadMetrics && \([\s\S]*?\)}/,
    `{/* Always show metrics section */}
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
                  {refreshingMetrics && (
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <CircularProgress size={16} sx={{ mr: 1 }} />
                      <Typography variant="caption" color="text.secondary">
                        Updating...
                      </Typography>
                    </Box>
                  )}
                </Box>`
  );

  // Write the fixed file
  fs.writeFile(appJsPath, fixedContent, 'utf8', (err) => {
    if (err) {
      console.error(`Error writing file: ${err}`);
      return;
    }
    console.log('Successfully fixed the syntax error in App.js!');
  });
});