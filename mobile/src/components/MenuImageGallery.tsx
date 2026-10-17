import { useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { MenuImage } from '../menuTypes';

type Props = {
  images: MenuImage[];
};

export function MenuImageGallery({ images }: Props) {
  const [failedURLs, setFailedURLs] = useState<string[]>([]);
  const availableImages = images.filter(
    (image) => !failedURLs.includes(image.large_url || image.url_original),
  );

  if (!availableImages.length) {
    return (
      <View style={styles.placeholder}>
        <Text style={styles.placeholderText}>등록된 메뉴 사진이 없습니다.</Text>
      </View>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={styles.gallery}
      horizontal
      showsHorizontalScrollIndicator={false}
    >
      {availableImages.map((image, index) => {
        const url = image.large_url || image.url_original;
        return (
          <Image
            accessibilityLabel={`메뉴 사진 ${index + 1}`}
            key={`${image.image_id || url}-${index}`}
            onError={() => setFailedURLs((current) => [...current, url])}
            resizeMode="cover"
            source={{ uri: url }}
            style={styles.image}
          />
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  gallery: { gap: 10, paddingHorizontal: 20 },
  image: { backgroundColor: '#E9E5DD', borderRadius: 18, height: 220, width: 290 },
  placeholder: {
    alignItems: 'center',
    backgroundColor: '#E9E5DD',
    borderRadius: 18,
    height: 150,
    justifyContent: 'center',
    marginHorizontal: 20,
  },
  placeholderText: { color: '#777F7A', fontSize: 13 },
});
