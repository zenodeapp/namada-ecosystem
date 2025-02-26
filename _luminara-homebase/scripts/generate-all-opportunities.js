const fs = require('fs');
const path = require('path');

// Définir le dossier des opportunités et le fichier de sortie
const opportunitiesFolder = './opportunities';
const outputFile = path.join(opportunitiesFolder, 'all_opportunities.json');

const opportunities = [];

// Lire tous les fichiers JSON dans le dossier des opportunités
fs.readdirSync(opportunitiesFolder).forEach(file => {
    if (path.extname(file) === '.json' && file !== 'all_opportunities.json') {
        const filePath = path.join(opportunitiesFolder, file);
        try {
            const opportunity = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            opportunities.push(opportunity);
            console.log(`✔️ Chargé : ${file}`);
        } catch (error) {
            console.error(`❌ Erreur lors de la lecture de ${file} :`, error.message);
        }
    }
});

// Écrire toutes les opportunités dans un seul fichier JSON
fs.writeFileSync(outputFile, JSON.stringify(opportunities, null, 2), 'utf-8');
console.log(`🚀 Fichier ${outputFile} généré avec ${opportunities.length} opportunités.`);
