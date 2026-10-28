import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import safar.basic.morphology.stemmer.factory.StemmerFactory;
import safar.basic.morphology.stemmer.interfaces.IStemmer;
import safar.basic.morphology.stemmer.model.WordStemmerAnalysis;

/**
 * Prétraitement du texte arabe (identique à la version Python) :
 * 1. suppression des diacritiques et du tatwil ;
 * 2. tokenisation (suites de lettres arabes) ;
 * 3. normalisation : alef maqsura -> ya ; hamzas -> alef nu ;
 * 4. suppression des mots vides et des mots d'une lettre ;
 * 5. (option) racinisation avec le Light10Stemmer de SAFAR.
 */
public class Preprocesseur {
    // U+064B-U+0652 (tashkil), U+0670 (alef suscrit), U+0640 (tatwil)
    private static final Pattern DIACRITIQUES = Pattern.compile("[\u064B-\u0652\u0670\u0640]");
    // U+0621-U+064A : lettres arabes
    private static final Pattern TOKEN = Pattern.compile("[\u0621-\u064A]+");
    // hamza, alef madda, alef hamza (dessus/dessous), waw hamza, ya hamza
    private static final Pattern HAMZA = Pattern.compile("[\u0621\u0622\u0623\u0624\u0625\u0626]");

    private final String stemming;               // "none" ou "light10"
    private final Set<String> stop = new HashSet<>();
    private final Map<String, String> cache = new HashMap<>();
    private static final String VIDE = "";       // marqueur « mot rejeté » dans le cache
    private final IStemmer stemmer;

    public Preprocesseur(Path fichierStopwords, String stemming) throws IOException {
        if (!stemming.equals("none") && !stemming.equals("light10"))
            throw new IllegalArgumentException("stemming doit valoir none ou light10");
        this.stemming = stemming;
        for (String l : Files.readAllLines(fichierStopwords, StandardCharsets.UTF_8)) {
            l = l.trim();
            if (!l.isEmpty()) stop.add(normaliser(l));
        }
        this.stemmer = stemming.equals("light10") ? StemmerFactory.getLight10Implementation() : null;
    }

    public String getStemming() { return stemming; }

    /** alef maqsura (U+0649) -> ya (U+064A) ; hamzas -> alef (U+0627). */
    public static String normaliser(String mot) {
        return HAMZA.matcher(mot.replace('\u0649', '\u064A')).replaceAll("\u0627");
    }

    private String racine(String mot) {
        List<WordStemmerAnalysis> r = stemmer.stem(mot);
        if (r.isEmpty() || r.get(0).getListStemmerAnalysis().isEmpty()) return "";
        return r.get(0).getListStemmerAnalysis().get(0).getMorpheme();
    }

    private String traiterMot(String mot) {
        String n = normaliser(mot);
        if (n.length() < 2 || stop.contains(n)) return VIDE;
        String s = stemming.equals("light10") ? racine(mot) : n;
        if (s.length() < 2 || stop.contains(s)) return VIDE;
        return s;
    }

    public List<String> tokens(String texte) {
        texte = DIACRITIQUES.matcher(texte).replaceAll("");
        List<String> res = new ArrayList<>();
        Matcher m = TOKEN.matcher(texte);
        while (m.find()) {
            String mot = m.group();
            String s = cache.computeIfAbsent(mot, this::traiterMot);
            if (!s.isEmpty()) res.add(s);
        }
        return res;
    }
}
