const fs = require('fs');
const path = require('path');

// Define the opportunities folder and the output file
const opportunitiesFolder = './opportunities';
const outputFile = path.join(opportunitiesFolder, 'all_opportunities.json');

const opportunities = [];

// Read all JSON files in the opportunities folder
fs.readdirSync(opportunitiesFolder).forEach(file => {
    if (
        path.extname(file) === '.json' &&                 // Only JSON files
        !file.startsWith('_') &&                           // Exclude files starting with an underscore (e.g., _opportunity_model.json)
        file !== 'all_opportunities.json'                  // Exclude the aggregated file itself
    ) {
        const filePath = path.join(opportunitiesFolder, file);
        try {
            const opportunity = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            opportunities.push(opportunity);
            console.log(`✔️ Loaded: ${file}`);
        } catch (error) {
            console.error(`❌ Error reading ${file}:`, error.message);
        }
    } else {
        console.log(`⏭️ Skipped: ${file}`);
    }
});

// Write all valid opportunities to a single JSON file
fs.writeFileSync(outputFile, JSON.stringify(opportunities, null, 2), 'utf-8');
console.log(`🚀 File ${outputFile} generated with ${opportunities.length} opportunities.`);
