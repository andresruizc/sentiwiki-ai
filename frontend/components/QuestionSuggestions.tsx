"use client";

import { Button } from "@/components/ui/button";
import { Sparkles, ArrowRight } from "lucide-react";
import { useState, useEffect, useRef } from "react";

interface QuestionSuggestionsProps {
  onSelectQuestion: (question: string) => void;
}

// Pool of questions to rotate through
const QUESTION_POOL = [
  "What is Sentinel-1 and what is it used for?",
  "What are the differences between Sentinel-1, Sentinel-2, and Sentinel-3?",
  "What applications can Sentinel-1 be used for?",
  "What is the spatial resolution of Sentinel-1 in IW mode?",
  "What acquisition modes does Sentinel-1 have?",
  "What is the swath width of Sentinel-2?",
  "What spectral bands does Sentinel-2 MSI have?",
  "What is the revisit period of Sentinel-2?",
  "What Level-1 products does Sentinel-1 generate?",
  "What is the temporal resolution of Sentinel-3?",
  "How is Sentinel-2 used for agricultural monitoring?",
  "Can Sentinel-1 detect changes in the Earth's surface?",
  "What applications does Sentinel-3 have for oceanography?",
  "How is Sentinel-2 used for flood mapping?",
  "What is the difference between GRD and SLC products?",
  "Which Sentinel mission can see through clouds?",
];

const QUESTIONS_PER_VIEW = 4;
const ROTATION_INTERVAL = 5000; // 5 seconds

export function QuestionSuggestions({ onSelectQuestion }: QuestionSuggestionsProps) {
  const [currentQuestions, setCurrentQuestions] = useState<string[]>([]);
  const [visibleQuestions, setVisibleQuestions] = useState<number[]>([]);
  const [isRotating, setIsRotating] = useState(false);
  const rotationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isVisibleRef = useRef(true);

  // Get random questions from the pool
  const getRandomQuestions = () => {
    const shuffled = [...QUESTION_POOL].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, QUESTIONS_PER_VIEW);
  };

  // Initialize with random questions
  useEffect(() => {
    setCurrentQuestions(getRandomQuestions());
  }, []);

  // Show questions with staggered animation
  useEffect(() => {
    if (currentQuestions.length === 0) return;
    
    // Reset visible questions
    setVisibleQuestions([]);
    
    // Show new questions with delay
    const delay = 200;
    
    setTimeout(() => {
      currentQuestions.forEach((_, index) => {
        setTimeout(() => {
          setVisibleQuestions((prev) => {
            // Avoid duplicates
            if (prev.includes(index)) return prev;
            return [...prev, index];
          });
        }, index * 100);
      });
    }, delay);
  }, [currentQuestions]);

  // Handle visibility change to pause/resume rotation
  useEffect(() => {
    const handleVisibilityChange = () => {
      isVisibleRef.current = !document.hidden;
      if (document.hidden) {
        // Pause rotation when tab is hidden
        if (rotationIntervalRef.current) {
          clearInterval(rotationIntervalRef.current);
          rotationIntervalRef.current = null;
        }
      }
      // Rotation will resume automatically when the main rotation effect detects visibility
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  // Rotate questions periodically
  useEffect(() => {
    const startRotation = () => {
      if (rotationIntervalRef.current) {
        clearInterval(rotationIntervalRef.current);
      }

      rotationIntervalRef.current = setInterval(() => {
        if (!isVisibleRef.current) return;
        
        // Start rotation - fade out
        setIsRotating(true);
        
        // After fade out, change questions
        setTimeout(() => {
          const newQuestions = getRandomQuestions();
          setCurrentQuestions(newQuestions);
          
          // Reset rotation state to allow fade in
          setTimeout(() => {
            setIsRotating(false);
          }, 100);
        }, 300);
      }, ROTATION_INTERVAL);
    };

    // Start rotation after initial questions are shown
    const timer = setTimeout(() => {
      startRotation();
    }, 2000); // Wait 2 seconds after initial load

    return () => {
      clearTimeout(timer);
      if (rotationIntervalRef.current) {
        clearInterval(rotationIntervalRef.current);
      }
    };
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-6 justify-center">
        <Sparkles className="h-4 w-4 text-primary animate-pulse drop-shadow-sm" />
        <h3 className="text-sm font-semibold bg-gradient-to-r from-foreground to-primary bg-clip-text text-transparent">
          Suggested Questions
        </h3>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {currentQuestions.map((question, index) => {
          const isVisible = visibleQuestions.includes(index);
          
          return (
            <Button
              key={`${question}-${index}`}
              variant="ghost"
              onClick={() => onSelectQuestion(question)}
              className={`
                group relative w-full py-2.5 px-3 text-left h-full min-h-[80px]
                bg-gradient-to-br from-card to-card/90 hover:from-card/95 hover:to-card border border-border/50 hover:border-primary/40
                rounded-xl transition-all duration-500 ease-out
                hover:shadow-lg hover:-translate-y-1.5 backdrop-blur-sm
                whitespace-normal items-center flex flex-row justify-center
                ${isVisible && !isRotating
                  ? 'opacity-100 translate-x-0 translate-y-0'
                  : 'opacity-0 -translate-x-8 translate-y-4'
                }
                ${isRotating ? 'pointer-events-none' : ''}
              `}
              style={{
                transitionDelay: isRotating ? '0ms' : `${index * 100}ms`,
              }}
            >
              <div className="flex items-center gap-2 w-full flex-1">
                <div className="flex-1 min-w-0 pr-0 overflow-hidden text-center">
                  <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors whitespace-normal break-words leading-relaxed">
                    {question}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all flex-shrink-0 opacity-0 group-hover:opacity-100" />
              </div>
            </Button>
          );
        })}
      </div>
    </div>
  );
}

