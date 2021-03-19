from __future__ import with_statement
import threading

# Thread safe list of tracker data pushed to GSheet in batches
class ConcurrentList():
    items = []
    number_of_items_in_batch = 49

    def __init__(self, numberOfItemsInBatch):
        self.lock = threading.Lock()
        self.items = []
        self.number_of_items_in_batch = numberOfItemsInBatch - 1    # index based so subtract 1

    def add(self, item):
        with self.lock:
            self.items.append(item)

    def getAll(self):
        with self.lock:
            itemsToReturn = self.items[:self.number_of_items_in_batch]
            del self.items[:self.number_of_items_in_batch]
        return itemsToReturn