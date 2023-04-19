from app import webapp, memcache
import random

def applyRandomReplacementPolicy(required_size):
    keys = []
    memCache_list = list(memcache.items())
    # params in memcache {'data', 'size', 'access_time': datetime.now(eastern)}
    while required_size > 0:
        key, params = random.choice(memCache_list)
        required_size -= params.get('size')
        keys.append(key)
        memCache_list.remove((key, params))

    return keys

def applyLeastRecentUsedPolicy(required_size):
    keys = []
    # sorting the list based on the access time attribute
    memCache_list = sorted(memcache.items(),key=lambda x: x[1]['access_time'],reverse=True)
    
    while required_size > 0:
        key, params = memCache_list[-1]
        required_size -= params.get('size')
        keys.append(key)
        memCache_list.remove((key, params))
        
    return keys
