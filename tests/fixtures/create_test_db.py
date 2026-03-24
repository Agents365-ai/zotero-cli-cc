"""Generate a minimal Zotero-compatible SQLite test fixture."""

import sqlite3
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
DB_PATH = FIXTURE_DIR / "zotero.sqlite"


def create_test_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Core schema (simplified from Zotero source)
    c.executescript("""
        CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY, type TEXT NOT NULL, editable INT NOT NULL DEFAULT 1, filesEditable INT NOT NULL DEFAULT 1);
        INSERT INTO libraries VALUES (1, 'user', 1, 1);

        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT NOT NULL);
        INSERT INTO itemTypes VALUES (2, 'journalArticle');
        INSERT INTO itemTypes VALUES (3, 'book');
        INSERT INTO itemTypes VALUES (26, 'note');
        INSERT INTO itemTypes VALUES (14, 'attachment');
        INSERT INTO itemTypes VALUES (37, 'preprint');

        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT NOT NULL);
        INSERT INTO fields VALUES (1, 'url');
        INSERT INTO fields VALUES (4, 'title');
        INSERT INTO fields VALUES (6, 'abstractNote');
        INSERT INTO fields VALUES (14, 'date');
        INSERT INTO fields VALUES (26, 'DOI');

        CREATE TABLE items (
            itemID INTEGER PRIMARY KEY,
            itemTypeID INT NOT NULL REFERENCES itemTypes(itemTypeID),
            dateAdded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            libraryID INT NOT NULL REFERENCES libraries(libraryID),
            key TEXT NOT NULL UNIQUE
        );

        CREATE TABLE itemData (itemID INT NOT NULL, fieldID INT NOT NULL, valueID INT NOT NULL, PRIMARY KEY (itemID, fieldID));
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT NOT NULL);

        CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT NOT NULL);
        INSERT INTO creatorTypes VALUES (1, 'author');
        INSERT INTO creatorTypes VALUES (2, 'editor');

        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT NOT NULL);
        CREATE TABLE itemCreators (itemID INT NOT NULL, creatorID INT NOT NULL, creatorTypeID INT NOT NULL DEFAULT 1, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (itemID, creatorID, creatorTypeID, orderIndex));

        CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE itemTags (itemID INT NOT NULL, tagID INT NOT NULL, type INT NOT NULL DEFAULT 0, PRIMARY KEY (itemID, tagID));

        CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT NOT NULL, parentCollectionID INT, libraryID INT NOT NULL, key TEXT NOT NULL UNIQUE);
        CREATE TABLE collectionItems (collectionID INT NOT NULL, itemID INT NOT NULL, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (collectionID, itemID));

        CREATE TABLE itemNotes (itemID INT PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);

        CREATE TABLE itemAttachments (
            itemID INT PRIMARY KEY,
            parentItemID INT,
            linkMode INT,
            contentType TEXT,
            charsetID INT,
            path TEXT
        );

        CREATE TABLE itemRelations (itemID INT NOT NULL, predicateID INT NOT NULL, object TEXT NOT NULL, PRIMARY KEY (itemID, predicateID, object));
        CREATE TABLE relationPredicates (predicateID INTEGER PRIMARY KEY, predicate TEXT NOT NULL UNIQUE);
        INSERT INTO relationPredicates VALUES (1, 'dc:relation');

        CREATE TABLE fulltextItemWords (wordID INT NOT NULL, itemID INT NOT NULL, PRIMARY KEY (wordID, itemID));
        CREATE TABLE fulltextWords (wordID INTEGER PRIMARY KEY, word TEXT NOT NULL UNIQUE);

        CREATE TABLE deletedItems (
            itemID INTEGER PRIMARY KEY,
            dateDeleted DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (itemID) REFERENCES items(itemID) ON DELETE CASCADE
        );
        CREATE INDEX deletedItems_dateDeleted ON deletedItems(dateDeleted);

        CREATE TABLE version (schema TEXT PRIMARY KEY, version INT NOT NULL);
        INSERT INTO version VALUES ('userdata', 120);
    """)

    # Test data: 2 journal articles, 1 book
    # Item 1: "Attention Is All You Need"
    c.execute("INSERT INTO items VALUES (1, 2, '2024-01-01', '2024-01-02', '2024-01-02', 1, 'ATTN001')")
    c.execute("INSERT INTO itemDataValues VALUES (1, 'Attention Is All You Need')")
    c.execute("INSERT INTO itemDataValues VALUES (2, 'We propose a new architecture...')")
    c.execute("INSERT INTO itemDataValues VALUES (3, '2017')")
    c.execute("INSERT INTO itemDataValues VALUES (4, '10.5555/attention')")
    c.execute("INSERT INTO itemData VALUES (1, 4, 1)")  # title
    c.execute("INSERT INTO itemData VALUES (1, 6, 2)")  # abstract
    c.execute("INSERT INTO itemData VALUES (1, 14, 3)")  # date
    c.execute("INSERT INTO itemData VALUES (1, 26, 4)")  # DOI
    c.execute("INSERT INTO creators VALUES (1, 'Ashish', 'Vaswani')")
    c.execute("INSERT INTO creators VALUES (2, 'Noam', 'Shazeer')")
    c.execute("INSERT INTO itemCreators VALUES (1, 1, 1, 0)")
    c.execute("INSERT INTO itemCreators VALUES (1, 2, 1, 1)")
    c.execute("INSERT INTO tags VALUES (1, 'transformer')")
    c.execute("INSERT INTO tags VALUES (2, 'attention')")
    c.execute("INSERT INTO tags VALUES (3, 'NLP')")
    c.execute("INSERT INTO itemTags VALUES (1, 1, 0)")
    c.execute("INSERT INTO itemTags VALUES (1, 2, 0)")

    # Item 2: "BERT: Pre-training of Deep Bidirectional Transformers"
    c.execute("INSERT INTO items VALUES (2, 2, '2024-02-01', '2024-02-02', '2024-02-02', 1, 'BERT002')")
    c.execute("INSERT INTO itemDataValues VALUES (5, 'BERT: Pre-training of Deep Bidirectional Transformers')")
    c.execute("INSERT INTO itemDataValues VALUES (6, 'We introduce BERT...')")
    c.execute("INSERT INTO itemDataValues VALUES (7, '2019')")
    c.execute("INSERT INTO itemDataValues VALUES (8, '10.5555/bert')")
    c.execute("INSERT INTO itemData VALUES (2, 4, 5)")
    c.execute("INSERT INTO itemData VALUES (2, 6, 6)")
    c.execute("INSERT INTO itemData VALUES (2, 14, 7)")
    c.execute("INSERT INTO itemData VALUES (2, 26, 8)")
    c.execute("INSERT INTO creators VALUES (3, 'Jacob', 'Devlin')")
    c.execute("INSERT INTO itemCreators VALUES (2, 3, 1, 0)")
    c.execute("INSERT INTO itemTags VALUES (2, 1, 0)")  # transformer
    c.execute("INSERT INTO itemTags VALUES (2, 3, 0)")  # NLP

    # Item 3: Book "Deep Learning"
    c.execute("INSERT INTO items VALUES (3, 3, '2024-03-01', '2024-03-02', '2024-03-02', 1, 'DEEP003')")
    c.execute("INSERT INTO itemDataValues VALUES (9, 'Deep Learning')")
    c.execute("INSERT INTO itemDataValues VALUES (10, 'An MIT Press book...')")
    c.execute("INSERT INTO itemDataValues VALUES (11, '2016')")
    c.execute("INSERT INTO itemData VALUES (3, 4, 9)")
    c.execute("INSERT INTO itemData VALUES (3, 6, 10)")
    c.execute("INSERT INTO itemData VALUES (3, 14, 11)")
    c.execute("INSERT INTO creators VALUES (4, 'Ian', 'Goodfellow')")
    c.execute("INSERT INTO itemCreators VALUES (3, 4, 1, 0)")

    # Item 4: Preprint "Scaling Laws for Neural Language Models"
    c.execute("INSERT INTO items VALUES (6, 37, '2024-04-01', '2024-04-02', '2024-04-02', 1, 'SCAL006')")
    c.execute("INSERT INTO itemDataValues VALUES (12, 'Scaling Laws for Neural Language Models')")
    c.execute("INSERT INTO itemDataValues VALUES (13, 'We study scaling laws...')")
    c.execute("INSERT INTO itemDataValues VALUES (14, '2020')")
    c.execute("INSERT INTO itemData VALUES (6, 4, 12)")  # title
    c.execute("INSERT INTO itemData VALUES (6, 6, 13)")  # abstract
    c.execute("INSERT INTO itemData VALUES (6, 14, 14)")  # date
    c.execute("INSERT INTO creators VALUES (5, 'Jared', 'Kaplan')")
    c.execute("INSERT INTO itemCreators VALUES (6, 5, 1, 0)")
    c.execute("INSERT INTO tags VALUES (4, 'scaling')")
    c.execute("INSERT INTO itemTags VALUES (6, 4, 0)")

    # Collections
    c.execute("INSERT INTO collections VALUES (1, 'Machine Learning', NULL, 1, 'COLML01')")
    c.execute("INSERT INTO collections VALUES (2, 'Transformers', 1, 1, 'COLTR02')")
    c.execute("INSERT INTO collectionItems VALUES (1, 1, 0)")
    c.execute("INSERT INTO collectionItems VALUES (1, 2, 0)")
    c.execute("INSERT INTO collectionItems VALUES (2, 1, 0)")
    c.execute("INSERT INTO collectionItems VALUES (1, 3, 0)")
    c.execute("INSERT INTO collectionItems VALUES (1, 6, 0)")

    # Notes
    c.execute("INSERT INTO items VALUES (4, 26, '2024-01-03', '2024-01-03', '2024-01-03', 1, 'NOTE004')")
    c.execute(
        "INSERT INTO itemNotes VALUES (4, 1, '<p>This paper introduces the transformer architecture.</p>', 'Transformer note')"
    )

    # Attachment (PDF) for item 1
    c.execute("INSERT INTO items VALUES (5, 14, '2024-01-01', '2024-01-01', '2024-01-01', 1, 'ATCH005')")
    c.execute("INSERT INTO itemAttachments VALUES (5, 1, 0, 'application/pdf', NULL, 'storage:attention.pdf')")

    # Relations: item 1 and item 2 are related
    c.execute("INSERT INTO itemRelations VALUES (1, 1, 'http://zotero.org/users/local/BERT002')")

    # Fulltext index for item 1
    c.execute("INSERT INTO fulltextWords VALUES (1, 'transformer')")
    c.execute("INSERT INTO fulltextWords VALUES (2, 'attention')")
    c.execute("INSERT INTO fulltextWords VALUES (3, 'mechanism')")
    c.execute("INSERT INTO fulltextItemWords VALUES (1, 5)")  # attachment itemID
    c.execute("INSERT INTO fulltextItemWords VALUES (2, 5)")
    c.execute("INSERT INTO fulltextItemWords VALUES (3, 5)")

    # Item 7: Trashed item "Old Survey Paper"
    c.execute("INSERT INTO items VALUES (7, 2, '2023-06-01', '2023-06-02', '2023-06-02', 1, 'TRSH007')")
    c.execute("INSERT INTO itemDataValues VALUES (15, 'Old Survey of Neural Networks')")
    c.execute("INSERT INTO itemDataValues VALUES (16, '2010')")
    c.execute("INSERT INTO itemData VALUES (7, 4, 15)")  # title
    c.execute("INSERT INTO itemData VALUES (7, 14, 16)")  # date
    c.execute("INSERT INTO creators VALUES (6, 'John', 'Smith')")
    c.execute("INSERT INTO itemCreators VALUES (7, 6, 1, 0)")
    c.execute("INSERT INTO deletedItems VALUES (7, '2024-03-01 12:00:00')")

    # Item 8: Duplicate of ATTN001 (same DOI)
    c.execute("INSERT INTO items VALUES (8, 2, '2024-05-01', '2024-05-02', '2024-05-02', 1, 'DUPE008')")
    c.execute("INSERT INTO itemDataValues VALUES (17, 'Attention Is All You Need (duplicate)')")
    c.execute("INSERT INTO itemDataValues VALUES (18, '10.5555/attention')")  # Same DOI as ATTN001
    c.execute("INSERT INTO itemData VALUES (8, 4, 17)")  # title
    c.execute("INSERT INTO itemData VALUES (8, 26, 18)")  # DOI

    conn.commit()
    conn.close()
    print(f"Created test DB at {DB_PATH}")


if __name__ == "__main__":
    create_test_db()
